/* Include before main in Mesa's air_metal_test.c. */
static bool
vbcap_u32(FILE *file, unsigned *value)
{
   unsigned char bytes[4];
   if (fread(bytes, 1, sizeof(bytes), file) != sizeof(bytes))
      return false;
   *value = bytes[0] | (unsigned)bytes[1] << 8 |
            (unsigned)bytes[2] << 16 | (unsigned)bytes[3] << 24;
   return true;
}

static bool
vbcap_buffer(FILE *file, struct rwa_device *device, size_t length,
             struct rwa_buffer **out, char *why)
{
   if (!length)
      return true;
   if (length > 16u * 1024 * 1024)
      return false;
   *out = rwa_buffer_create(device, length, why, WHY);
   return *out && fread(rwa_buffer_map(*out), 1, length, file) == length;
}

static struct rwa_texture *
vbcap_texture(struct rwa_device *device, const unsigned *dimensions,
              unsigned levels, unsigned usage, char *why)
{
   const struct rwa_texture_shape shape = {
      .width = dimensions[0], .height = dimensions[1],
      .pixel_format = dimensions[2], .type = MTL_TEXTURE_TYPE_2D,
      .depth = 1, .array_length = 1, .mip_levels = levels,
      .sample_count = 1, .usage = usage,
   };
   if (!shape.width || !shape.height || shape.width > 4096 || shape.height > 4096 ||
       (shape.pixel_format != 80 && shape.pixel_format != 81))
      return NULL;
   return rwa_texture_create(device, &shape, why, WHY);
}

static int
run_vbcap(const char *library, const char *vertex, const char *fragment,
          const char *capture, const char *output)
{
   char why[WHY] = "";
   const char *stage = "opening capture";
   FILE *file = fopen(capture, "rb"), *image = NULL;
   struct metallib lib = {0};
   struct rwa_device *device = NULL;
   struct rwa_render *render = NULL;
   struct rwa_buffer *index = NULL, *buffers[2][7] = {{0}};
   struct rwa_texture *target = NULL, *textures[5] = {0};
   unsigned char *pixels = NULL;
   int status = 1;
   char magic[8];
   unsigned header[9];
   if (!file)
      goto done;
   stage = "reading capture header";
   if (fread(magic, 1, sizeof(magic), file) != sizeof(magic) ||
       memcmp(magic, "VBCAP1\0\0", sizeof(magic)))
      goto done;
   for (unsigned i = 0; i < COUNT_OF(header); i++)
      if (!vbcap_u32(file, &header[i]))
         goto done;
   const unsigned index_type = header[7], index_count = header[8];
   if (index_type == UINT32_MAX ? index_count != 0 :
       (index_type > 1 || index_count != header[5] || !index_count ||
        index_count > 4u * 1024 * 1024))
      goto done;

   stage = "opening softpipe";
   setenv("RWA_SOFTWARE", "1", 1);
   device = rwa_device_open(why, sizeof(why));
   if (!device)
      goto done;
   stage = "loading captured buffers";
   if (!vbcap_buffer(file, device, (size_t)index_count * (index_type == 1 ? 4 : 2),
                     &index, why))
      goto done;
   const unsigned slots[2][3] = {{1, 2, 3}, {1, 5, 6}};
   for (unsigned s = 0; s < 2; s++) {
      for (unsigned i = 0; i < 3; i++) {
         unsigned slot, length;
         if (!vbcap_u32(file, &slot) || slot != slots[s][i] ||
             !vbcap_u32(file, &length) || (!s && !length) ||
             !vbcap_buffer(file, device, length, &buffers[s][slot], why))
            goto done;
      }
   }

   stage = "loading captured textures";
   const unsigned origin[3] = {0, 0, 0};
   for (unsigned slot = 3; slot <= 4; slot++) {
      unsigned texture[5];
      for (unsigned i = 0; i < COUNT_OF(texture); i++)
         if (!vbcap_u32(file, &texture[i]))
            goto done;
      if (texture[0] != slot || !texture[4] || texture[4] > 12)
         goto done;
      textures[slot] = vbcap_texture(device, texture + 1, texture[4],
                                     MTL_USAGE_SHADER_READ, why);
      if (!textures[slot])
         goto done;
      for (unsigned level = 0; level < texture[4]; level++) {
         unsigned width = texture[1] >> level, height = texture[2] >> level;
         unsigned extent[3] = {width ? width : 1, height ? height : 1, 1};
         size_t length = (size_t)extent[0] * extent[1] * 4;
         pixels = malloc(length);
         if (!pixels || fread(pixels, 1, length, file) != length ||
             rwa_texture_write(textures[slot], level, 0, origin, extent,
                               pixels, extent[0] * 4, why, sizeof(why)))
            goto done;
         free(pixels);
         pixels = NULL;
      }
   }
   if (fgetc(file) != EOF || ferror(file))
      goto done;

   stage = "loading vertex and fragment functions";
   const uint8_t *vs, *fs;
   size_t vs_size, fs_size;
   char vs_name[256], fs_name[256];
   if (!load_metallib(library, &lib) ||
       !find_function(&lib, vertex, vs_name, sizeof(vs_name), &vs, &vs_size) ||
       !find_function(&lib, fragment, fs_name, sizeof(fs_name), &fs, &fs_size))
      goto done;
   stage = "creating render target and pipeline";
   target = vbcap_texture(device, header, 1, MTL_USAGE_SHADER_READ | 4, why);
   if (!target)
      goto done;
   const struct rwa_render_shape shape = {
      .color_count = 1, .color_format = {header[2]}, .sample_count = 1,
      .vertex_attribute = {
         [0] = {.format = 31, .offset = 0, .buffer_index = 1},
         [1] = {.format = 29, .offset = 16, .buffer_index = 1},
         [2] = {.format = 29, .offset = 24, .buffer_index = 1},
      },
      .vertex_layout = {[1] = {.stride = 48, .step_function = 1}},
   };
   struct rwa_render_info info = {0};
   render = rwa_render_create(device, vs, vs_size, vs_name, fs, fs_size,
                              fs_name, &shape, &info, why, sizeof(why));
   if (!render)
      goto done;
   const struct rwa_vertex_stream streams[2] = {
      [1] = {.buffer = buffers[0][1]},
   };
   buffers[0][1] = NULL;
   const struct rwa_draw draw = {
      .color = &target, .color_count = 1,
      .clear_color = (const float[]){0, 0, 0, 0},
      .vertex = {.buffers = buffers[0], .buffer_count = 4},
      .fragment = {.buffers = buffers[1], .buffer_count = 7,
                   .textures = textures, .texture_count = 5},
      .primitive = header[3], .vertex_start = header[4], .vertex_count = header[5],
      .base_vertex = (int32_t)header[6],
      .index_buffer = index, .index_type = index ? index_type : 0,
      .vertex_streams = streams, .vertex_stream_count = COUNT_OF(streams),
   };
   stage = "drawing captured geometry";
   const int draw_status = rwa_render_draw(render, &draw, why, sizeof(why));
   buffers[0][1] = streams[1].buffer;
   if (draw_status)
      goto done;

   stage = "reading back BGRA render target";
   const unsigned extent[3] = {header[0], header[1], 1};
   const size_t length = (size_t)extent[0] * extent[1] * 4;
   pixels = malloc(length);
   if (!pixels || rwa_texture_read(target, 0, 0, origin, extent, pixels,
                                   extent[0] * 4, why, sizeof(why)))
      goto done;
   stage = "writing PAM image";
   image = fopen(output, "wb");
   if (!image || fprintf(image, "P7\nWIDTH %u\nHEIGHT %u\nDEPTH 4\n"
                         "MAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n",
                         extent[0], extent[1]) < 0)
      goto done;
   for (size_t i = 0; i < length; i += 4) {
      unsigned char blue = pixels[i];
      pixels[i] = pixels[i + 2];
      pixels[i + 2] = blue;
   }
   if (fwrite(pixels, 1, length, image) == length && fflush(image) == 0)
      status = 0;

done:
   if (status)
      fprintf(stderr, "VBCAP replay failed while %s%s%s\n", stage,
              why[0] ? ": " : "", why);
   if (image)
      fclose(image);
   if (file)
      fclose(file);
   free(pixels);
   if (render)
      rwa_render_destroy(render);
   if (target)
      rwa_texture_destroy(target);
   for (unsigned i = 3; i <= 4; i++)
      if (textures[i])
         rwa_texture_destroy(textures[i]);
   for (unsigned s = 0; s < 2; s++)
      for (unsigned i = 0; i < 7; i++)
         if (buffers[s][i])
            rwa_buffer_destroy(buffers[s][i]);
   if (index)
      rwa_buffer_destroy(index);
   if (device)
      rwa_device_close(device);
   free(lib.bytes);
   return status;
}
