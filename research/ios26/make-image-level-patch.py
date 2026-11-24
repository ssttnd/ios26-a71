"""Generate userspace/native-metal/ios26-image-write-levels.patch against the donor tree.

Metal's texture.write(value, coord, lod) may name the mip level at run time (Mercury's
VariableBlurrer::downsample builds its chain that way). A Gallium image view is one level,
so every texture written at a level other than a constant 0 gets up to eight extra image
slots, slot base+k bound to level k of the same texture, and the store picks its slot from
the level. Applies after ios26-mip-views.patch and ios26-blur-attachments.patch.
"""
from pathlib import Path
from difflib import unified_diff

# Base = donor (has ios26-mip-views applied) + ios26-blur-attachments, LF: CI applies this patch on top of both.
r = Path('research/ios26/native-glass-src/base-mip-blur')
changes = []

_astc = []
for _i, (_w, _h) in enumerate([(4, 4), (5, 4), (5, 5), (6, 5), (6, 6)]):
    _astc += [(186 + _i, f'ASTC_{_w}x{_h}_sRGB', f'ASTC_{_w}x{_h}_SRGB'), (204 + _i, f'ASTC_{_w}x{_h}_LDR', f'ASTC_{_w}x{_h}')]
for _i, (_w, _h) in enumerate([(8, 5), (8, 6), (8, 8), (10, 5), (10, 6), (10, 8), (10, 10), (12, 10), (12, 12)]):
    _astc += [(192 + _i, f'ASTC_{_w}x{_h}_sRGB', f'ASTC_{_w}x{_h}_SRGB'), (210 + _i, f'ASTC_{_w}x{_h}_LDR', f'ASTC_{_w}x{_h}')]
ASTC_ROWS = ''.join(f'   {{ {m:3d}, "MTLPixelFormat{n}", PIPE_FORMAT_{g} }},\n' for m, n, g in sorted(_astc))


def edit(name, *pairs):
    old = (r / name).read_text(encoding='utf-8')
    new = old
    for a, b in pairs:
        assert new.count(a) == 1, (name, a, new.count(a))
        new = new.replace(a, b)
    changes.append(f'diff --git a/{name} b/{name}\n' +
                   ''.join(unified_diff(old.splitlines(True), new.splitlines(True), f'a/{name}', f'b/{name}')))


edit('tools/mesa/air/nir_air.h',
     ('struct air_shader_info {\n',
      '#define AIR_TEXTURE_PRESENCE_UBO 31u /* Metal buffer indices end at 30. */\n'
      'struct air_shader_info {\n'
      '   bool uses_texture_presence;\n'),
     ('   const char *name;    /* declared Metal function-constant name */\n',
      '   const char *name;    /* declared Metal function-constant name */\n'
      '   uint64_t bits_hi;   /* upper half of a packed vector, zero for scalars */\n'),
     ('   unsigned native_read_bytes; /* proved constant-offset UBO extent, zero = unknown */\n};',
      '''   unsigned native_read_bytes; /* proved constant-offset UBO extent, zero = unknown */

   /* A written texture is one Gallium image view, which is one mip level. image_slot is
    * the image binding (Metal's index unless this is a level alias); mip_level is the
    * level a level alias binds; level_base/level_count, on the texture's own entry, say
    * where its aliases are when the shader writes a level that is not a constant 0.
    */
   unsigned image_slot;
   unsigned mip_level;
   unsigned level_base, level_count;
};'''))

edit('tools/mesa/air/air_to_nir.c',
     ('''      case AIR_RESOURCE_CONSTANT_BUFFER:
         c.nir->info.num_ubos = MAX2(c.nir->info.num_ubos, r->index + 1);''',
      '''      case AIR_RESOURCE_CONSTANT_BUFFER:
         if (c.info->uses_texture_presence && r->index == AIR_TEXTURE_PRESENCE_UBO) {
            air_error(&c, "a constant buffer overlaps the texture-presence binding");
            if (error)
               *error = ralloc_strdup(mem_ctx, c.error);
            ralloc_free(c.nir);
            ralloc_free(ctx);
            return NULL;
         }
         c.nir->info.num_ubos = MAX2(c.nir->info.num_ubos, r->index + 1);'''),
     ('   c.nir->scratch_size = c.scratch_size;\n',
      '   if (c.info->uses_texture_presence)\n'
      '      c.nir->info.num_ubos = MAX2(c.nir->info.num_ubos, AIR_TEXTURE_PRESENCE_UBO + 1);\n'
      '   c.nir->scratch_size = c.scratch_size;\n'),
     ('''   return glsl_vector_type(bits == 16 ? GLSL_TYPE_FLOAT16 :
                           bits == 64 ? GLSL_TYPE_UINT64 : GLSL_TYPE_UINT,
''',
      '''   return glsl_vector_type(bits == 1 ? GLSL_TYPE_BOOL :
                           bits == 8 ? GLSL_TYPE_UINT8 :
                           bits == 16 ? GLSL_TYPE_FLOAT16 :
                           bits == 64 ? GLSL_TYPE_UINT64 : GLSL_TYPE_UINT,
'''),
     ('                 struct air_val **argv, bool *is_param)\n',
      '                 struct air_val **argv, bool *is_param, nir_def **pointer_offsets)\n'),
     ('''    * A pointer carrying a byte offset is refused instead: that offset is an
    * nir_def of the CALLER's impl, and using it here would be the same
    * cross-function def/use that the globals used to cause.
''',
      '''    * A dynamic byte offset travels as a scalar NIR parameter; only the resource
    * identity is specialized into the callee.
'''),
     ('''      if (ptr && argv[i]->kind == AIR_VAL_PTR && argv[i]->ptr.offset &&
          !fold_scalar(c, argv[i]->ptr.offset, &const_offset)) {
         air_error(c, "intrinsic: a call passing a pointer at a computed offset as "
                      "argument %u, which would use the caller's own value here", i);
         return NULL;
      }
''',
      '''      if (ptr && argv[i]->kind == AIR_VAL_PTR && argv[i]->ptr.offset &&
          !fold_scalar(c, argv[i]->ptr.offset, &const_offset)) {
         const struct air_ptr *p = &argv[i]->ptr;
         if (!pointer_offsets || (p->class != AIR_PTR_UBO && p->class != AIR_PTR_SSBO &&
                                  p->class != AIR_PTR_SHARED && p->class != AIR_PTR_SCRATCH &&
                                  p->class != AIR_PTR_CONSTANT_DATA)) {
            air_error(c, "intrinsic: unsupported computed offset on pointer argument %u", i);
            return NULL;
         }
         pointer_offsets[i] = p->offset;
      }
'''),
     ('''         if (arg_is_flat(f, argv, is_param, i))
            declare_leaves(fn, &idx, argv[i]);
         continue;
''',
      '''         if (arg_is_flat(f, argv, is_param, i))
            declare_leaves(fn, &idx, argv[i]);
         else if (pointer_offsets && pointer_offsets[i])
            fn->params[idx++] = (nir_parameter){ .num_components = 1, .bit_size = 32 };
         continue;
'''),
     ('''            uint64_t bytes = 0;
            fold_scalar(c, a->ptr.offset, &bytes);   /* checked by the caller above */
            rp.offset = nir_imm_int(&c->b, bytes);
''',
      '''            if (pointer_offsets && pointer_offsets[i]) {
               rp.offset = nir_load_param(&c->b, pidx++);
            } else {
               uint64_t bytes = 0;
               fold_scalar(c, a->ptr.offset, &bytes);   /* checked by the caller above */
               rp.offset = nir_imm_int(&c->b, bytes);
            }
'''),
     ('''   nir_function *fn = translate_callee(c, f, argv, is_param);
   if (!fn)
      return false;   /* translate_callee has said why */

   unsigned bits = air_nir_bit_size(c, rt);
''',
      '''   nir_function *fn = translate_callee(c, f, argv, is_param, NULL);
   if (!fn)
      return false;   /* translate_callee has said why */

   unsigned bits = air_nir_bit_size(c, rt);
'''),
     ('         nir_function *fn = translate_callee(c, f, NULL, NULL);\n',
      '         nir_function *fn = translate_callee(c, f, NULL, NULL, NULL);\n'),
     ('static bool\nmd_key_int(const struct air_md *node, const char *key, uint64_t *out)\n',
      '''static bool md_interface_int(struct air_ctx *, const struct air_md *, unsigned, uint64_t *);

static bool
md_key_int(const struct air_md *node, const char *key, uint64_t *out)
'''),
     ('      if (!md_int(node, rt_in + 1, &n))\n',
      '      if (!md_interface_int(c, node, rt_in + 1, &n))\n'),
     ('''      md_int(node, rt + 1, &n);
      md_int(node, rt + 2, &dual);
''',
      '''      if (rt + 1 < node->num_ops && node->ops[rt + 1] &&
          node->ops[rt + 1]->kind == AIR_MD_VALUE &&
          !md_interface_int(c, node, rt + 1, &n))
         return air_error(c, "interface: an air.render_target output without a target");
      if (n >= MAX_DRAW_BUFFERS)
         return air_error(c, "interface: air.render_target output %llu", (unsigned long long)n);
      md_int(node, rt + 2, &dual);
'''),
     ('''plan_globals(struct air_ctx *c)
{
   c->global_plan = rzalloc_array(c->mem_ctx, struct air_global_plan,
                                  MAX2(c->m->num_globals, 1));
''',
      '''plan_globals(struct air_ctx *c, bool samplers)
{
   if (!samplers) {
      if (c->global_plan)
         return;
      c->global_plan = rzalloc_array(c->mem_ctx, struct air_global_plan,
                                     MAX2(c->m->num_globals, 1));
   }
'''),
     ('''      const char *name = g->base.name ? g->base.name : "";

      /* llvm.compiler.used and llvm.global_ctors''',
      '''      const char *name = g->base.name ? g->base.name : "";
      const bool inline_sampler = !g->externally_initialized && !strncmp(name, "__air_sampler_state", 19);
      if (samplers != inline_sampler)
         continue;

      /* llvm.compiler.used and llvm.global_ctors'''),
     ('      } else if (!strncmp(name, "__air_sampler_state", 19)) {\n',
      '      } else if (inline_sampler) {\n'),
     ('''   if (!c->error[0])
      plan_static_constants(c);
}
''',
      '''   if (!samplers && !c->error[0])
      plan_static_constants(c);
}

/* Newer AIR can put a global reference in place of a literal target index.
 * Resolve it from specialized initializer bytes before assigning shader I/O.
 * Inline sampler indices are still assigned after the explicit arguments.
 */
static bool
md_interface_int(struct air_ctx *c, const struct air_md *node, unsigned i, uint64_t *out)
{
   if (md_int(node, i, out))
      return true;
   if (!node || i >= node->num_ops || !node->ops[i] || node->ops[i]->kind != AIR_MD_VALUE)
      return false;
   const struct air_value *v = node->ops[i]->value;
   if (!v || v->kind != AIR_VALUE_GLOBAL)
      return false;
   for (unsigned gi = 0; gi < c->m->num_globals; gi++) {
      const struct air_global *g = c->m->globals[gi];
      if (&g->base != v)
         continue;
      if (!g->value_type || g->value_type->kind != AIR_TYPE_INT ||
          !g->value_type->bits || g->value_type->bits > 64)
         return false;
      if (g->is_const && air_const_uint(g->init, out))
         return true;
      plan_globals(c, false);
      const struct air_global_plan *pl = &c->global_plan[gi];
      unsigned bytes = (g->value_type->bits + 7) / 8;
      if (!c->static_init_folded || !pl->shadow || pl->shadow_size < bytes)
         return false;
      uint64_t word = 0;
      for (unsigned b = 0; b < bytes; b++) {
         if (!pl->shadow_known[b])
            return false;
         word |= (uint64_t)pl->shadow[b] << (8 * b);
      }
      *out = word;
      return true;
   }
   return false;
}
'''),
     ('''   if (!c.error[0])
      plan_globals(&c);
''',
      '''   if (!c.error[0])
      plan_globals(&c, false);
   if (!c.error[0])
      plan_globals(&c, true);
'''),
     ('''static bool
translate_input(struct air_ctx *c, const struct air_md *node, unsigned *next_varying)
''',
      '''static bool
md_interface_disabled(struct air_ctx *c, const struct air_md *node)
{
   const struct air_md *predicate = md_key_node(node, "air.function_constant");
   uint64_t enabled;
   return predicate && md_interface_int(c, predicate, 0, &enabled) && !enabled;
}

static bool
translate_input(struct air_ctx *c, const struct air_md *node, unsigned *next_varying)
'''),
     ('''   const struct air_type *t = c->fn->args[param].type;

   /* resources */
''',
      '''   const struct air_type *t = c->fn->args[param].type;
   if (md_interface_disabled(c, node)) {
      if (t->kind == AIR_TYPE_POINTER) {
         const struct air_ptr unused = { .class = AIR_PTR_NONE, .pointee = t->elem };
         c->params[param] = air_val_ptr(c, unused);
      } else {
         c->params[param] = air_val_ssa(c, nir_undef(&c->b, air_nir_components(t),
                                                     air_nir_bit_size(c, t)));
      }
      return true;
   }

   /* resources */
'''),
     ('''   unsigned location = ~0u, index = 0;
   const char *name = md_key_str(node, "air.arg_name");
''',
      '''   if (md_interface_disabled(c, node)) {
      c->outputs[field].disabled = true;
      return true;
   }
   unsigned location = ~0u, index = 0;
   const char *name = md_key_str(node, "air.arg_name");
'''),
     ('''      for (unsigned i = 0; i < v->num_elems; i++) {
         if (!c->outputs[i].var)
''',
      '''      for (unsigned i = 0; i < v->num_elems; i++) {
         if (c->outputs[i].disabled)
            continue;
         if (!c->outputs[i].var)
'''),
     ('   if (!c->num_outputs || !c->outputs[0].var)\n',
      '   if (c->num_outputs && c->outputs[0].disabled)\n'
      '      return true;\n'
      '   if (!c->num_outputs || !c->outputs[0].var)\n'),
     ('''   if (_mesa_hash_table_num_entries(c.fns)) {
      NIR_PASS(_, c.nir, nir_inline_functions);
''',
      '''   if (_mesa_hash_table_num_entries(c.fns)) {
      /* The inliner expects helper returns to have been lowered. */
      NIR_PASS(_, c.nir, nir_lower_returns);
      NIR_PASS(_, c.nir, nir_inline_functions);
'''),
     ('''      /* A VECTOR function constant. Metal allows one and the GL-on-Metal
       * fragment shaders use two: `uchar3` opcode triples for the texture
       * combiners (`fc_color_opcodes0/1`, declared `<3 x i8>`).
       *
       * air_constant_value carries one 64-bit word per constant, so the
       * components have to be fields of it, and the packing is this frontend's
       * own interface with the runtime rather than something read out of
       * Apple's: component i sits at bit i*width, which is the word a memcpy
       * of the value would produce on this little-endian target. NOTHING HERE
       * MEASURES THAT -- every harness in tools/air supplies zero for every
       * constant, so all components are zero whatever the packing, and the
       * first thing that would tell a wrong packing from a right one is a
       * pipeline that sets one of these two constants.
       */
      if (comps * bits > 64)
         return air_error(c, "interface: a function constant of %u components of %u bits, "
                             "which does not fit the one word air_constant_value carries",
                          comps, bits), NULL;
      nir_def *fields[NIR_MAX_VEC_COMPONENTS];
      for (unsigned i = 0; i < comps; i++) {
         uint64_t mask = bits >= 64 ? ~0ull : (1ull << bits) - 1;
         fields[i] = nir_imm_intN_t(&c->b, (v->bits >> (i * bits)) & mask,
                                    as_bool ? 8 : bits);
      }
''',
      '''      /* Vector components are stored consecutively in two little-endian words.
       * The runtime supplies byte-sized storage for boolean components.
       */
      const unsigned width = as_bool ? 8 : bits;
      if (!width || width > 64 || 64 % width || comps > 128 / width)
         return air_error(c, "interface: function constant with %u components of %u bits exceeds packed storage",
                          comps, width), NULL;
      const uint64_t words[2] = { v->bits, v->bits_hi };
      const uint64_t mask = width == 64 ? ~0ull : (1ull << width) - 1;
      nir_def *fields[NIR_MAX_VEC_COMPONENTS];
      for (unsigned i = 0; i < comps; i++) {
         const unsigned bit = i * width;
         const uint64_t lane = (words[bit / 64] >> (bit % 64)) & mask;
         fields[i] = nir_imm_intN_t(&c->b, lane, width);
      }
'''),
     ('      .argbuf_set = ~0u, .argbuf_id = ~0u,\n   };\n   return &info->resources[info->num_resources++];',
      '      .argbuf_set = ~0u, .argbuf_id = ~0u,\n      .image_slot = index,\n   };\n   return &info->resources[info->num_resources++];'),
     ('''         c.nir->info.num_images = MAX2(c.nir->info.num_images, r->index + 1);
         BITSET_SET(c.nir->info.images_used, r->index);''',
      '''         c.nir->info.num_images = MAX2(c.nir->info.num_images, r->image_slot + 1);
         BITSET_SET(c.nir->info.images_used, r->image_slot);'''),
     # Mercury's VTMTSComputeFunction1x1 bitcasts i32 -> <4 x i8>. Any reshaping that keeps
     # the total bit count is the same little-endian move; NIR has it as nir_bitcast_vector.
     ('''      else
         return air_error(c, "instruction: a bitcast from %u x %u bits to %u x %u bits, "''',
      '''      else if (sn * sb == dn * db)
         res = nir_bitcast_vector(&c->b, x, db);
      else
         return air_error(c, "instruction: a bitcast from %u x %u bits to %u x %u bits, "'''),
     # Mercury passes a texture chosen at run time (a pointer phi) to a function of its
     # module. The callee is specialised per pointer, so the call is split: a goto_if on
     # the choice, one call per side, both joining before the rest of the block (the CFG
     # is unstructured here; nir_lower_goto_ifs orders it). Results go through the same
     # local variables; SSA arguments are fetched before the split so they dominate both.
     ('''/* A call of a function this module defines. The callee is translated as a
 * nir_function (above)''',
      '''/* A new block of the current impl, placed the way the switch lowering does */
static nir_block *
call_split_block(struct air_ctx *c)
{
   nir_block *nb = nir_block_create(c->nir);
   exec_list_push_tail(&c->b.impl->body, &nb->cf_node.node);
   nb->cf_node.parent = &c->b.impl->cf_node;
   return nb;
}

/* the first pointer chosen at run time in an argument, itself or inside a struct */
static struct air_val *
first_chosen_ptr(struct air_val *v)
{
   if (!v)
      return NULL;
   if (v->kind == AIR_VAL_PTR_SELECT && v->num_elems == 2)
      return v;
   if (v->kind == AIR_VAL_AGG) {
      for (unsigned i = 0; i < v->num_elems; i++) {
         struct air_val *s = first_chosen_ptr(v->elems[i]);
         if (s)
            return s;
      }
   }
   return NULL;
}

/* the argument with that choice made: sel replaced by side, structs copied */
static struct air_val *
with_choice_made(struct air_ctx *c, struct air_val *v, struct air_val *sel,
                 struct air_val *side)
{
   if (v == sel)
      return side;
   if (!v || v->kind != AIR_VAL_AGG)
      return v;
   struct air_val *agg = air_val_agg(c, v->num_elems);
   for (unsigned i = 0; i < v->num_elems; i++)
      agg->elems[i] = with_choice_made(c, v->elems[i], sel, side);
   return agg;
}

static bool
emit_module_call(struct air_ctx *c, const struct air_inst *in, const struct air_function *f,
                 const char *name, struct air_val **argv, nir_def **ssa,
                 nir_variable *tmp, nir_variable **fields)
{
   for (unsigned i = 0; i < f->num_args; i++) {
      struct air_val *sel = first_chosen_ptr(argv[i]);
      if (!sel)
         continue;
      nir_block *side_block[2] = { call_split_block(c), call_split_block(c) };
      nir_block *join = call_split_block(c);
      nir_goto_if(&c->b, side_block[0], sel->def, side_block[1]);
      for (unsigned s = 0; s < 2; s++) {
         struct air_val **side = rzalloc_array(c->mem_ctx, struct air_val *,
                                               MAX2(f->num_args, 1));
         memcpy(side, argv, sizeof(*side) * f->num_args);
         side[i] = with_choice_made(c, argv[i], sel, sel->elems[s]);
         c->b.cursor = nir_after_block(side_block[s]);
         if (!emit_module_call(c, in, f, name, side, ssa, tmp, fields))
            return false;
         nir_goto(&c->b, join);
      }
      c->b.cursor = nir_after_block(join);
      return true;
   }

   bool *is_param = rzalloc_array(c->mem_ctx, bool, MAX2(f->num_args, 1));
   nir_def **pointer_offsets = rzalloc_array(c->mem_ctx, nir_def *, MAX2(f->num_args, 1));
   nir_function *fn = translate_callee(c, f, argv, is_param, pointer_offsets);
   if (!fn)
      return false;   /* translate_callee has said why */

   const struct air_type *rt = f->fn_type->elem;
   nir_call_instr *call = nir_call_instr_create(c->nir, fn);
   unsigned idx = 0;
   if (fields) {
      for (unsigned i = 0; i < rt->num_members; i++)
         if (fields[i])
            call->params[idx++] =
               nir_src_for_ssa(&nir_build_deref_var(&c->b, fields[i])->def);
   } else if (tmp) {
      call->params[idx++] = nir_src_for_ssa(&nir_build_deref_var(&c->b, tmp)->def);
   }
   /* operand 0 is the callee; the arguments follow it */
   for (unsigned i = 0; i < f->num_args; i++) {
      if (!is_param[i]) {
         if (arg_is_flat(f, argv, is_param, i))
            pass_leaves(call, &idx, argv[i]);
         else if (pointer_offsets[i])
            call->params[idx++] = nir_src_for_ssa(pointer_offsets[i]);
         continue;
      }
      nir_def *a = ssa[i] ? ssa[i] : air_get_ssa(c, in->operands[i + 1]);
      if (!a)
         return air_error(c, "intrinsic: argument %u of %s is not a value this can pass",
                          i, name);
      call->params[idx++] = nir_src_for_ssa(a);
   }
   nir_builder_instr_insert(&c->b, &call->instr);
   return true;
}

/* A call of a function this module defines. The callee is translated as a
 * nir_function (above)'''),
     ('''   bool *is_param = rzalloc_array(c->mem_ctx, bool, MAX2(f->num_args, 1));
   for (unsigned i = 0; i < f->num_args; i++) {
      argv[i] = air_get(c, in->operands[i + 1]);
      if (!argv[i])
         return false;
   }

   nir_function *fn = translate_callee(c, f, argv, is_param);
   if (!fn)
      return false;   /* translate_callee has said why */

   const struct air_type *rt''',
      '''   nir_def **ssa = rzalloc_array(c->mem_ctx, nir_def *, MAX2(f->num_args, 1));
   for (unsigned i = 0; i < f->num_args; i++) {
      argv[i] = air_get(c, in->operands[i + 1]);
      if (!argv[i])
         return false;
      if (argv[i]->kind == AIR_VAL_SSA)
         ssa[i] = argv[i]->def;
   }

   const struct air_type *rt'''),
     ('''   nir_call_instr *call = nir_call_instr_create(c->nir, fn);
   unsigned idx = 0;
   if (ret_struct) {
      for (unsigned i = 0; i < rt->num_members; i++) {
         if (!ret_member_is_number(rt->members[i]))
            continue;
         fields[i] = nir_local_variable_create(c->b.impl,
                                               param_glsl_type(c, rt->members[i]),
                                               "callret");
         call->params[idx++] =
            nir_src_for_ssa(&nir_build_deref_var(&c->b, fields[i])->def);
      }
   } else if (has_ret) {
      tmp = nir_local_variable_create(c->b.impl, param_glsl_type(c, rt), "callret");
      call->params[idx++] = nir_src_for_ssa(&nir_build_deref_var(&c->b, tmp)->def);
   }
   /* operand 0 is the callee; the arguments follow it */
   for (unsigned i = 0; i < f->num_args; i++) {
      if (!is_param[i]) {
         if (arg_is_flat(f, argv, is_param, i))
            pass_leaves(call, &idx, argv[i]);
         continue;
      }
      nir_def *a = air_get_ssa(c, in->operands[i + 1]);
      if (!a)
         return air_error(c, "intrinsic: argument %u of %s is not a value this can pass",
                          i, name);
      call->params[idx++] = nir_src_for_ssa(a);
   }
   nir_builder_instr_insert(&c->b, &call->instr);
''',
      '''   if (ret_struct) {
      for (unsigned i = 0; i < rt->num_members; i++)
         if (ret_member_is_number(rt->members[i]))
            fields[i] = nir_local_variable_create(c->b.impl,
                                                  param_glsl_type(c, rt->members[i]),
                                                  "callret");
   } else if (has_ret) {
      tmp = nir_local_variable_create(c->b.impl, param_glsl_type(c, rt), "callret");
   }
   if (!emit_module_call(c, in, f, name, argv, ssa, tmp, fields))
      return false;
'''),
     ('''/* A phi of POINTERS, resolved rather than carried in a register.
 *
 * A pointer here is *(which resource, which byte offset)* decided while
 * translating, so it has no bits to put in a register and a phi of two of them
 * is not a value NIR can hold. It need not be: LLVM duplicates a
 * `getelementptr` onto two paths and phis the copies back, so both operands
 * name the same member -- 207 of the pointer phis in Resident Evil 4's library
 * are exactly that, and not one names two different members.
 *
 * Refused when they differ. This COULD go through the AIR_VAL_PTR_SELECT
 * machinery that already loads both sides and selects the values, but nothing
 * in reach needs it, a texture or a sampler is not a value that path can load,
 * and an untested path is worse than a refusal.
 *
 * `reachable` is why this is sound rather than optimistic: the blocks are
 * walked in reverse post order, so an operand coming in over a BACK edge has
 * not been translated yet. Skipping an operand merely because it is missing
 * would accept a loop-carried pointer by ignoring the edge that changes it, so
 * a missing operand from a reachable block is a refusal and only an edge the
 * entry cannot reach at all is passed over.
 */
''',
      '''/* Represent pointer phis by a place selector or a buffer-relative byte offset.
 * A pending operand must be checked once the incoming edge has been translated.
 */
'''),
     ('''static bool
resolve_pointer_phi(struct air_ctx *c, const struct air_inst *in,
                    const struct air_edges *edges)
{''',
      '''struct air_ptr_phi {
   nir_def *reg;
   struct air_val *offset_base;
   unsigned n;
   struct air_val *v[8];
};
#define PTR_PHI_KEY(in) ((const void *)((const char *)(in) + 1))

/* The resolved places a pointer operand may name: itself, or every leaf of a pointer
 * chosen at run time (a select, or an earlier phi of this kind), each place once. */
static bool
ptr_phi_leaves(struct air_val *v, struct air_val **out, unsigned *n, unsigned max)
{
   if (!v)
      return false;
   if (v->kind == AIR_VAL_PTR) {
      for (unsigned j = 0; j < *n; j++)
         if (same_ptr(&out[j]->ptr, &v->ptr))
            return true;
      if (*n == max)
         return false;
      out[(*n)++] = v;
      return true;
   }
   if (v->kind == AIR_VAL_PTR_SELECT && v->num_elems == 2)
      return ptr_phi_leaves(v->elems[0], out, n, max) &&
             ptr_phi_leaves(v->elems[1], out, n, max);
   return false;
}

/* Which of the phi's places an operand brings, as a value: a constant for a resolved
 * pointer, a bcsel on the choice's own condition for one chosen at run time. Built at the
 * end of the predecessor, where that condition is defined. */
static nir_def *
ptr_phi_index(struct air_ctx *c, const struct air_ptr_phi *pp, struct air_val *v)
{
   if (!v)
      return NULL;
   if (v->kind == AIR_VAL_PTR) {
      for (unsigned j = 0; j < pp->n; j++)
         if (same_ptr(&pp->v[j]->ptr, &v->ptr))
            return nir_imm_int(&c->b, (int)j);
      return NULL;
   }
   if (v->kind == AIR_VAL_PTR_SELECT && v->num_elems == 2) {
      nir_def *a = ptr_phi_index(c, pp, v->elems[0]);
      nir_def *b = ptr_phi_index(c, pp, v->elems[1]);
      return a && b ? nir_bcsel(&c->b, v->def, a, b) : NULL;
   }
   return NULL;
}

static bool
ptr_phi_same_buffer(const struct air_ptr *a, const struct air_ptr *b)
{
   return a->class == b->class && a->binding == b->binding && a->is_image == b->is_image;
}

static nir_def *
ptr_phi_offset(struct air_ctx *c, const struct air_ptr *base, struct air_val *v)
{
   if (!v)
      return NULL;
   if (v->kind == AIR_VAL_PTR)
      return ptr_phi_same_buffer(base, &v->ptr) ? ptr_offset(c, v->ptr) : NULL;
   if (v->kind == AIR_VAL_PTR_SELECT && v->num_elems == 2) {
      nir_def *a = ptr_phi_offset(c, base, v->elems[0]);
      nir_def *b = ptr_phi_offset(c, base, v->elems[1]);
      return a && b ? nir_bcsel(&c->b, v->def, a, b) : NULL;
   }
   return NULL;
}

static bool
resolve_pointer_phi(struct air_ctx *c, const struct air_inst *in,
                    const struct air_edges *edges)
{
   struct air_val *leaves[8];
   unsigned n = 0;
   bool pending_operand = false;'''),
     ('''      if (!e)
         return air_error(c, "instruction: a phi of pointers whose operand comes in over "
                             "a loop edge, so which resource it is depends on the "
                             "iteration");
''',
      '''      if (!e) {
         pending_operand = true;
         continue;
      }
'''),
     ('''      struct air_val *v = e->data;
      if (!v || v->kind != AIR_VAL_PTR)
         return air_error(c, "instruction: a phi of pointers one of whose operands is "
                             "%s", v && v->kind == AIR_VAL_PTR_SELECT
                                      ? "itself a pointer chosen at run time"
                                      : "not a resolved pointer");
      if (!first)
         first = v;
      else if (!same_ptr(&first->ptr, &v->ptr))
         return air_error(c, "instruction: a phi between pointers that name different "
                             "places, which would have to be chosen at run time");
   }
   if (!first)
      return air_error(c, "instruction: a phi of pointers with no reachable operand");
   air_set(c, &in->base, first);
   return true;
}''',
      '''      struct air_val *v = e->data;
      if (!ptr_phi_leaves(v, leaves, &n, ARRAY_SIZE(leaves)))
         return air_error(c, "instruction: a phi of pointers one of whose operands is %s",
                          n == ARRAY_SIZE(leaves) ? "one of more than eight places"
                                                  : "not a resolved pointer");
      if (!first)
         first = leaves[0];
   }
   if (!first)
      return air_error(c, "instruction: a phi of pointers with no reachable operand");
   struct hash_entry *pe = _mesa_hash_table_search(c->phi_regs, PTR_PHI_KEY(in));
   struct air_ptr_phi *pp = pe ? pe->data : NULL;
   if (pending_operand) {
      /* A loop can advance a pointer through one buffer. Carry its offset in
       * the phi register and verify all incoming buffer bindings once the
       * predecessors have been translated.
       */
      struct air_ptr place = first->ptr;
      if (!pp || (place.class != AIR_PTR_UBO && place.class != AIR_PTR_SSBO))
         return air_error(c, "instruction: a loop-carried pointer phi without a buffer base");
      for (unsigned j = 0; j < n; j++)
         if (!ptr_phi_same_buffer(&place, &leaves[j]->ptr))
            return air_error(c, "instruction: a loop-carried pointer phi selects different buffers");
      pp->offset_base = first;
      place.offset = nir_load_reg(&c->b, pp->reg);
      air_set(c, &in->base, air_val_ptr(c, place));
      return true;
   }
   if (n < 2) {
      if (pp)
         pp->n = 0;
      air_set(c, &in->base, first);
      return true;
   }
   /* buffers are loaded on both sides and selected; a texture or sampler is split per
    * place by texture_op (air_intrinsics.c); an argument-buffer member has neither */
   for (unsigned j = 0; j < n; j++)
      if (!pp || leaves[j]->ptr.class == AIR_PTR_ARGBUF)
         return air_error(c, "instruction: a phi between pointers that name different "
                             "places, which would have to be chosen at run time");
   pp->n = n;
   memcpy(pp->v, leaves, n * sizeof(leaves[0]));
   nir_def *sel = nir_load_reg(&c->b, pp->reg);
   struct air_val *r = pp->v[pp->n - 1];
   for (int j = (int)pp->n - 2; j >= 0; j--)
      r = air_val_ptr_select(c, nir_ieq_imm(&c->b, sel, j), pp->v[j], r);
   air_set(c, &in->base, r);
   return true;
}'''),
     ('''         if (in->op != AIR_OP_PHI || in->base.type->kind == AIR_TYPE_POINTER)
            continue;''',
      '''         if (in->op != AIR_OP_PHI)
            continue;
         if (in->base.type->kind == AIR_TYPE_POINTER) {
            struct air_ptr_phi *pp = rzalloc(c->mem_ctx, struct air_ptr_phi);
            pp->reg = nir_decl_reg(&entry, 1, 32, 0);
            _mesa_hash_table_insert(c->phi_regs, PTR_PHI_KEY(in), pp);
            continue;
         }'''),
     ('''         if (in->base.type->kind == AIR_TYPE_STRUCT ||
             in->base.type->kind == AIR_TYPE_ARRAY)
            return air_error(c, "instruction: a phi of %s, which NIR has no register for",
                             in->base.type->kind == AIR_TYPE_STRUCT ? "a struct"
                                                                    : "an array");
''',
      '''         if (in->base.type->kind == AIR_TYPE_STRUCT || in->base.type->kind == AIR_TYPE_ARRAY) {
            struct air_val *regs = aggregate_phi_regs(c, &entry, in->base.type);
            if (!regs)
               return air_error(c, "instruction: an aggregate phi with a non-numeric member");
            _mesa_hash_table_insert(c->phi_regs, in, regs);
            continue;
         }
'''),
     ('''         air_set(c, &in->base,
                 air_val_ssa(c, nir_load_reg(&c->b, e->data)));
''',
      '''         if (in->base.type->kind == AIR_TYPE_STRUCT || in->base.type->kind == AIR_TYPE_ARRAY)
            air_set(c, &in->base, aggregate_phi_load(c, e->data));
         else
            air_set(c, &in->base, air_val_ssa(c, nir_load_reg(&c->b, e->data)));
'''),
     ('''static bool
translate_body(struct air_ctx *c)
''',
      '''/* Aggregate phis use one register per numeric leaf, with the same edge
 * writes and block-entry loads as the scalar phi path.
 */
static struct air_val *
aggregate_phi_regs(struct air_ctx *c, nir_builder *entry, const struct air_type *type)
{
   if (ret_member_is_number(type))
      return air_val_ssa(c, nir_decl_reg(entry, air_nir_components(type), air_nir_bit_size(c, type), 0));
   const bool is_struct = type->kind == AIR_TYPE_STRUCT;
   if (!is_struct && (type->kind != AIR_TYPE_ARRAY || type->count > UINT32_MAX))
      return NULL;
   struct air_val *regs = air_val_agg(c, is_struct ? type->num_members : type->count);
   for (unsigned i = 0; i < regs->num_elems; i++) {
      regs->elems[i] = aggregate_phi_regs(c, entry, is_struct ? type->members[i] : type->elem);
      if (!regs->elems[i])
         return NULL;
   }
   return regs;
}

static struct air_val *
aggregate_phi_load(struct air_ctx *c, const struct air_val *regs)
{
   if (regs->kind == AIR_VAL_SSA)
      return air_val_ssa(c, nir_load_reg(&c->b, regs->def));
   struct air_val *value = air_val_agg(c, regs->num_elems);
   for (unsigned i = 0; i < value->num_elems; i++)
      value->elems[i] = aggregate_phi_load(c, regs->elems[i]);
   return value;
}

static bool
aggregate_phi_store(struct air_ctx *c, const struct air_val *regs, const struct air_val *value)
{
   if (regs->kind == AIR_VAL_SSA) {
      nir_intrinsic_instr *decl = nir_reg_get_decl(regs->def);
      const unsigned comps = nir_intrinsic_num_components(decl);
      const unsigned bits = nir_intrinsic_bit_size(decl);
      if (value && (value->kind != AIR_VAL_SSA || value->def->num_components != comps ||
                    value->def->bit_size != bits))
         return false;
      nir_store_reg(&c->b, value ? value->def : nir_undef(&c->b, comps, bits), regs->def);
      return true;
   }
   if (value && (value->kind != AIR_VAL_AGG || value->num_elems != regs->num_elems))
      return false;
   for (unsigned i = 0; i < regs->num_elems; i++)
      if (!aggregate_phi_store(c, regs->elems[i], value ? value->elems[i] : NULL))
         return false;
   return true;
}

static bool
translate_body(struct air_ctx *c)
'''),
     ('''            nir_def *val = air_get_ssa(c, in->operands[k]);
            if (!val)
               return false;
            nir_store_reg(&c->b, val, re->data);
''',
      '''            if (in->base.type->kind == AIR_TYPE_STRUCT || in->base.type->kind == AIR_TYPE_ARRAY) {
               struct air_val *val = air_get(c, in->operands[k]);
               if (!val || !aggregate_phi_store(c, re->data, val))
                  return air_error(c, "instruction: an aggregate phi with an incompatible operand");
            } else {
               nir_def *val = air_get_ssa(c, in->operands[k]);
               if (!val)
                  return false;
               nir_store_reg(&c->b, val, re->data);
            }
'''),
     ('''         struct hash_entry *re = _mesa_hash_table_search(c->phi_regs, in);
         if (!re)
            continue; /* a phi in an unreachable block, or one of pointers */''',
      '''         if (in->base.type->kind == AIR_TYPE_POINTER) {
            struct hash_entry *pe = _mesa_hash_table_search(c->phi_regs, PTR_PHI_KEY(in));
            struct air_ptr_phi *pp = pe ? pe->data : NULL;
            if (!pp || (!pp->offset_base && pp->n < 2))
               continue; /* resolved to one place, or never reached */
            for (unsigned k = 0; k < in->num_operands; k++) {
               struct hash_entry *ce = _mesa_hash_table_search(c->phi_cursors, in->targets[k]);
               if (!ce || !edge_possible(&edges, in->targets[k]->index, bi))
                  continue;
               struct hash_entry *e = _mesa_hash_table_search(c->values, in->operands[k]);
               struct air_val *v = e ? e->data : NULL;
               c->b.cursor = *(nir_cursor *)ce->data;
               nir_def *incoming = pp->offset_base ? ptr_phi_offset(c, &pp->offset_base->ptr, v) :
                                                     ptr_phi_index(c, pp, v);
               if (!incoming)
                  return air_error(c, "instruction: a pointer phi operand cannot be represented by its "
                                      "resolved places or loop buffer");
               nir_store_reg(&c->b, incoming, pp->reg);
               *(nir_cursor *)ce->data = c->b.cursor;
            }
            continue;
         }
         struct hash_entry *re = _mesa_hash_table_search(c->phi_regs, in);
         if (!re)
            continue; /* a phi in an unreachable block */'''),
     # Visible function tables. RenderBox's uber_fragment takes one when its has_function_table
     # constant is set (Mercury, once it is told Apple6), and the pipeline was refused outright
     # ("interface: input air.function_constant"). No function pointers here: the table is an
     # empty resource and a call through a pointer returns zero, so only custom effects are lost.
     ('   /* resources */\n   if (md_key(node, "air.buffer") >= 0) {',
      '''   if (md_key(node, "air.visible_function_table") >= 0 ||
       md_key(node, "air.intersection_function_table") >= 0) {
      air_note(c, "parameter %u is a function table: no function pointers on this GPU, so a "
                  "call through it returns zero (custom effects draw nothing)", (unsigned)param);
      if (t->kind == AIR_TYPE_POINTER) {
         const struct air_ptr none = { .class = AIR_PTR_NONE, .pointee = t->elem };
         c->params[param] = air_val_ptr(c, none);
      } else {
         c->params[param] = air_val_ssa(c, nir_undef(&c->b, air_nir_components(t),
                                                     air_nir_bit_size(c, t)));
      }
      return true;
   }

   /* resources */
   if (md_key(node, "air.buffer") >= 0) {'''),
     ('         return air_error(c, "instruction: a call through a pointer");\n',
      '''      {
         /* a visible function: no function pointers here, the result is zero */
         const struct air_type *rt = in->base.type;
         if (rt && rt->kind != AIR_TYPE_VOID) {
            struct air_constant z = { .base = { .kind = AIR_VALUE_CONSTANT, .type = rt },
                                      .ckind = AIR_CONST_NULL };
            struct air_val *zero = air_constant_val(c, &z);
            if (!zero)
               return false;
            air_set(c, &in->base, zero);
         }
         air_note(c, "a call through a function pointer returns zero (no function pointers)");
         return true;
      }
'''),
     # loop pointer phi from an unbound buffer (RenderBox gradients)
     (r'''      struct air_ptr place = first->ptr;
      if (!pp || (place.class != AIR_PTR_UBO && place.class != AIR_PTR_SSBO))''',
      r'''      struct air_ptr place = first->ptr;
      if (pp && place.class == AIR_PTR_NONE) {
         /* a pointer into nothing (a buffer the constants left unbound): advancing it is
          * still nothing. The back edges are checked to stay nothing with the phi stores. */
         for (unsigned j = 0; j < n; j++)
            if (leaves[j]->ptr.class != AIR_PTR_NONE)
               return air_error(c, "instruction: a loop-carried pointer phi mixes an unbound "
                                   "pointer with a buffer");
         pp->offset_base = first;
         air_set(c, &in->base, air_val_ptr(c, place));
         return true;
      }
      if (!pp || (place.class != AIR_PTR_UBO && place.class != AIR_PTR_SSBO))'''),
     # loop pointer phi from an unbound buffer (RenderBox gradients)
     (r'''               c->b.cursor = *(nir_cursor *)ce->data;
               nir_def *incoming = pp->offset_base ? ptr_phi_offset(c, &pp->offset_base->ptr, v) :''',
      r'''               if (pp->offset_base && pp->offset_base->ptr.class == AIR_PTR_NONE) {
                  if (!v || v->kind != AIR_VAL_PTR || v->ptr.class != AIR_PTR_NONE)
                     return air_error(c, "instruction: a loop-carried pointer phi starts unbound "
                                         "and is advanced into a buffer");
                  continue;
               }
               c->b.cursor = *(nir_cursor *)ce->data;
               nir_def *incoming = pp->offset_base ? ptr_phi_offset(c, &pp->offset_base->ptr, v) :'''),
     # name the global in the refusal
     ('''            air_error(c, "interface: an externally initialized variable that is not a "
                         "function constant");
''',
      '''            air_error(c, "interface: an externally initialized variable that is not a "
                         "function constant (%s)", name);
'''),
     # i1 as an index or integer operand (uber_fragment: invalid src bit size: 1)
     (r'''unsigned
air_nir_bit_size(struct air_ctx *c, const struct air_type *t)
{''',
      r'''/* An LLVM integer of one bit is a NIR boolean, and NIR's integer conversions,
 * arithmetic and ordered comparisons take no 1-bit operand ("invalid src bit
 * size: 1" on the device, from an extractelement indexed by a compare in
 * RenderBox's uber_fragment). Widen it the way LLVM extends it.
 */
static nir_def *
air_int32(nir_builder *b, nir_def *x, bool sign)
{
   if (x->bit_size == 1)
      return sign ? nir_ineg(b, nir_b2i32(b, x)) : nir_b2i32(b, x);
   return sign ? nir_i2i32(b, x) : nir_u2u32(b, x);
}

unsigned
air_nir_bit_size(struct air_ctx *c, const struct air_type *t)
{'''),
     # i1 as an index or integer operand (uber_fragment: invalid src bit size: 1)
     (r'''p = air_ptr_add(c, p, nir_imul_imm(&c->b, nir_u2u32(&c->b, first), stride));''',
      r'''p = air_ptr_add(c, p, nir_imul_imm(&c->b, air_int32(&c->b, first, true), stride));'''),
     # i1 as an index or integer operand (uber_fragment: invalid src bit size: 1)
     (r'''p = air_ptr_add(c, p, nir_imul_imm(&c->b, nir_u2u32(&c->b, idx), es));''',
      r'''p = air_ptr_add(c, p, nir_imul_imm(&c->b, air_int32(&c->b, idx, true), es));'''),
     # i1 as an index or integer operand (uber_fragment: invalid src bit size: 1)
     (r'''   if (is_float)
      c->b.exact = !(in->flags & (AIR_FMF_UNSAFE_ALGEBRA | AIR_FMF_REASSOC));

   switch (in->sub) {
   case AIR_BINOP_ADD:''',
      r'''   if (is_float)
      c->b.exact = !(in->flags & (AIR_FMF_UNSAFE_ALGEBRA | AIR_FMF_REASSOC));

   /* i1 arithmetic other than the bitwise three: in 32 bits, then the low bit */
   const bool narrow = !is_float && x->bit_size == 1 && in->sub != AIR_BINOP_AND &&
                       in->sub != AIR_BINOP_OR && in->sub != AIR_BINOP_XOR;
   if (narrow) {
      const bool sign = in->sub == AIR_BINOP_SDIV || in->sub == AIR_BINOP_SREM ||
                        in->sub == AIR_BINOP_ASHR;
      x = air_int32(&c->b, x, sign);
      y = air_int32(&c->b, y, sign);
   }

   switch (in->sub) {
   case AIR_BINOP_ADD:'''),
     # i1 as an index or integer operand (uber_fragment: invalid src bit size: 1)
     (r'''   case AIR_BINOP_SHL: res = nir_ishl(&c->b, x, nir_u2u32(&c->b, y)); break;
   case AIR_BINOP_LSHR: res = nir_ushr(&c->b, x, nir_u2u32(&c->b, y)); break;
   case AIR_BINOP_ASHR: res = nir_ishr(&c->b, x, nir_u2u32(&c->b, y)); break;''',
      r'''   case AIR_BINOP_SHL: res = nir_ishl(&c->b, x, air_int32(&c->b, y, false)); break;
   case AIR_BINOP_LSHR: res = nir_ushr(&c->b, x, air_int32(&c->b, y, false)); break;
   case AIR_BINOP_ASHR: res = nir_ishr(&c->b, x, air_int32(&c->b, y, false)); break;'''),
     # i1 as an index or integer operand (uber_fragment: invalid src bit size: 1)
     (r'''      return air_error(c, "instruction: binary operator %u", in->sub);
   }
   c->b.exact = was_exact;''',
      r'''      return air_error(c, "instruction: binary operator %u", in->sub);
   }
   if (narrow)
      res = nir_ine_imm(&c->b, nir_iand_imm(&c->b, res, 1), 0);
   c->b.exact = was_exact;'''),
     # i1 as an index or integer operand (uber_fragment: invalid src bit size: 1)
     (r'''   nir_def *res;
   switch (in->sub) {
   /* NaN never appears in these shaders''',
      r'''   nir_def *res;
   if (x->bit_size == 1 && in->sub != AIR_ICMP_EQ && in->sub != AIR_ICMP_NE &&
       (in->sub == AIR_ICMP_UGT || in->sub == AIR_ICMP_UGE || in->sub == AIR_ICMP_ULT ||
        in->sub == AIR_ICMP_ULE || in->sub == AIR_ICMP_SGT || in->sub == AIR_ICMP_SGE ||
        in->sub == AIR_ICMP_SLT || in->sub == AIR_ICMP_SLE)) {
      const bool sign = in->sub == AIR_ICMP_SGT || in->sub == AIR_ICMP_SGE ||
                        in->sub == AIR_ICMP_SLT || in->sub == AIR_ICMP_SLE;
      x = air_int32(&c->b, x, sign);
      y = air_int32(&c->b, y, sign);
   }
   switch (in->sub) {
   /* NaN never appears in these shaders'''),
     # i1 as an index or integer operand (uber_fragment: invalid src bit size: 1)
     (r'''air_set(c, &in->base, air_val_ssa(c, nir_vector_extract(&c->b, v, nir_u2u32(&c->b, i))));''',
      r'''air_set(c, &in->base, air_val_ssa(c, nir_vector_extract(&c->b, v, air_int32(&c->b, i, false))));'''),
     # i1 as an index or integer operand (uber_fragment: invalid src bit size: 1)
     (r'''air_val_ssa(c, nir_vector_insert(&c->b, v, x, nir_u2u32(&c->b, i))));''',
      r'''air_val_ssa(c, nir_vector_insert(&c->b, v, x, air_int32(&c->b, i, false))));'''),
     # inline samplers with the same state share a slot (uber_fragment: 17 slots > 16)
     (r'''         struct air_shader_info *info = c->info;
         info->resources = reralloc(c->mem_ctx, info->resources, struct air_resource,
                                    info->num_resources + 1);''',
      r'''         /* One sampler per distinct state: RenderBox's uber_fragment declares fifteen
          * inline samplers next to its two API ones, seventeen slots where the GPU has
          * sixteen, and most of them are the same state word. Same state, same slot.
          */
         {
            bool shared = false;
            for (unsigned k = 0; k < c->info->num_resources; k++) {
               const struct air_resource *o = &c->info->resources[k];
               if (o->kind == AIR_RESOURCE_SAMPLER && o->inline_sampler &&
                   o->sampler_state == word) {
                  pl->binding = o->index;
                  shared = true;
                  break;
               }
            }
            if (shared)
               continue;
         }
         struct air_shader_info *info = c->info;
         info->resources = reralloc(c->mem_ctx, info->resources, struct air_resource,
                                    info->num_resources + 1);'''))

edit('tools/mesa/air/air_private.h',
     ('      unsigned index;         /* dual-source index */\n',
      '      unsigned index;         /* dual-source index */\n'
      '      bool disabled;          /* specialized out of the shader interface */\n'))

edit('tools/mesa/air/air_intrinsics.c',
     # Mercury packs colour as Metal's pack_float_to_unorm10a2: saturate, scale by 1023 or
     # 3, round to nearest, R in the low ten bits and A in the top two. Its unpack is the
     # inverse. Both are spelt air.(un)pack.unorm.rgb10a2.<type>.
     ('''   } else if (!strcmp(op, "unpack") && n->num >= 2 &&
              !strcmp(n->part[1], "unorm4x8")) {''',
      '''   } else if (!strcmp(op, "pack") && n->num >= 2 &&
              (!strcmp(n->part[1], "unorm4x8") || !strcmp(n->part[1], "snorm4x8") ||
               !strcmp(n->part[1], "unorm2x16") || !strcmp(n->part[1], "snorm2x16"))) {
      /* Metal's pack_float_to_{u,s}norm{4x8,2x16}: GLSL's packUnorm4x8 and friends,
       * component 0 in the low bits, which is what NIR's opcodes define */
      nir_def *v = nir_f2f32(&c->b, a[0]);
      const char *k = n->part[1];
      r = !strcmp(k, "unorm4x8") ? nir_pack_unorm_4x8(&c->b, v) :
          !strcmp(k, "snorm4x8") ? nir_pack_snorm_4x8(&c->b, v) :
          !strcmp(k, "unorm2x16") ? nir_pack_unorm_2x16(&c->b, v) :
                                    nir_pack_snorm_2x16(&c->b, v);
   } else if (!strcmp(op, "unpack") && n->num >= 2 &&
              (!strcmp(n->part[1], "snorm4x8") || !strcmp(n->part[1], "unorm2x16") ||
               !strcmp(n->part[1], "snorm2x16"))) {
      nir_def *w = nir_u2u32(&c->b, a[0]);
      const char *k = n->part[1];
      r = !strcmp(k, "snorm4x8") ? nir_unpack_snorm_4x8(&c->b, w) :
          !strcmp(k, "unorm2x16") ? nir_unpack_unorm_2x16(&c->b, w) :
                                    nir_unpack_snorm_2x16(&c->b, w);
      if (air_nir_bit_size(c, in->base.type) == 16)
         r = nir_f2f16(&c->b, r);
   } else if ((!strcmp(op, "pack") || !strcmp(op, "unpack")) && n->num >= 3 &&
              !strcmp(n->part[1], "unorm") && !strcmp(n->part[2], "rgb10a2")) {
      if (!strcmp(op, "pack")) {
         nir_def *v = nir_fsat(&c->b, nir_f2f32(&c->b, a[0]));
         nir_def *q = nir_f2u32(&c->b, nir_fround_even(&c->b,
                          nir_fmul(&c->b, v, nir_imm_vec4(&c->b, 1023.0, 1023.0, 1023.0, 3.0))));
         r = nir_ior(&c->b,
                     nir_ior(&c->b, nir_channel(&c->b, q, 0),
                             nir_ishl_imm(&c->b, nir_channel(&c->b, q, 1), 10)),
                     nir_ior(&c->b, nir_ishl_imm(&c->b, nir_channel(&c->b, q, 2), 20),
                             nir_ishl_imm(&c->b, nir_channel(&c->b, q, 3), 30)));
      } else {
         nir_def *w = nir_u2u32(&c->b, a[0]);
         nir_def *ch[4];
         for (unsigned i = 0; i < 4; i++)
            ch[i] = nir_u2f32(&c->b, nir_ubitfield_extract(&c->b, w, nir_imm_int(&c->b, 10 * i),
                                                           nir_imm_int(&c->b, i < 3 ? 10 : 2)));
         r = nir_fmul(&c->b, nir_vec(&c->b, ch, 4),
                      nir_imm_vec4(&c->b, 1.0 / 1023.0, 1.0 / 1023.0, 1.0 / 1023.0, 1.0 / 3.0));
         if (air_nir_bit_size(c, in->base.type) == 16)
            r = nir_f2f16(&c->b, r);
      }
   } else if (!strcmp(op, "unpack") && n->num >= 2 &&
              !strcmp(n->part[1], "unorm4x8")) {'''),
     # sincos: the cosine leaves through a pointer (Metal's `thread T &cosval`) or, in a
     # struct-returning spelling, as the second member. Handled before math_op loads its
     # arguments as numbers, which a pointer is not.
     ('''   nir_def *a[4] = { 0 };
   for (unsigned i = 0; i < argc && i < 4; i++)''',
      '''   if (!strcmp(op, "fast_sincos") || !strcmp(op, "sincos")) {
      nir_def *x = air_get_ssa(c, in->operands[1]);
      if (!x)
         return false;
      *handled = true;
      nir_def *s = nir_fsin(&c->b, x), *co = nir_fcos(&c->b, x);
      if (in->base.type->kind == AIR_TYPE_STRUCT) {
         struct air_val *agg = rzalloc(c->mem_ctx, struct air_val);
         agg->kind = AIR_VAL_AGG;
         agg->num_elems = 2;
         agg->elems = rzalloc_array(c->mem_ctx, struct air_val *, 2);
         agg->elems[0] = air_val_ssa(c, s);
         agg->elems[1] = air_val_ssa(c, co);
         air_set(c, &in->base, agg);
         return true;
      }
      struct air_val *pv = argc >= 2 ? air_get(c, in->operands[2]) : NULL;
      if (!pv || pv->kind != AIR_VAL_PTR)
         return air_error(c, "intrinsic: air.%s without a pointer for the cosine", op);
      if (!air_store_ptr(c, pv->ptr, co, 0))
         return false;
      air_set(c, &in->base, air_val_ssa(c, s));
      return true;
   }

   nir_def *a[4] = { 0 };
   for (unsigned i = 0; i < argc && i < 4; i++)'''),
     # llvm.smax/smin/umin (Mercury: llvm.smax.i16; umax is in the blur patch) and
     # llvm.bswap (VideoToolbox's scaler)
     ('''   if (!strncmp(name, "llvm.fabs.", 10)) {''',
      '''   if (!strncmp(name, "llvm.smax.", 10) || !strncmp(name, "llvm.smin.", 10) ||
       !strncmp(name, "llvm.umin.", 10)) {
      nir_def *x = air_get_ssa(c, in->operands[1]);
      nir_def *y = air_get_ssa(c, in->operands[2]);
      if (!x || !y)
         return false;
      nir_def *r = !strncmp(name, "llvm.smax.", 10) ? nir_imax(&c->b, x, y) :
                   !strncmp(name, "llvm.smin.", 10) ? nir_imin(&c->b, x, y) :
                                                      nir_umin(&c->b, x, y);
      air_set(c, &in->base, air_val_ssa(c, r));
      return true;
   }
   if (!strncmp(name, "llvm.bswap.", 11)) {
      nir_def *x = air_get_ssa(c, in->operands[1]);
      if (!x)
         return false;
      unsigned bits = x->bit_size;
      nir_def *r = NULL;
      for (unsigned i = 0; i < bits / 8; i++) {
         nir_def *byte = nir_iand_imm(&c->b, nir_ushr_imm(&c->b, x, 8 * i), 0xff);
         byte = nir_ishl_imm(&c->b, byte, bits - 8 - 8 * i);
         r = r ? nir_ior(&c->b, r, byte) : byte;
      }
      if (!r)
         return air_error(c, "intrinsic: %s", name);
      air_set(c, &in->base, air_val_ssa(c, r));
      return true;
   }
   if (!strncmp(name, "llvm.fabs.", 10)) {'''),
     ('/* a constant i1/i32 argument, which these intrinsics use as flags */',
      '''/* The image slots a texture written at a run-time mip level uses: slot base+k is bound
 * to level k of the same texture (air_metal.c). Made once per texture, after every other
 * image binding, up to fifteen and never past the sixteen image slots the runtime has.
 */
#define AIR_IMAGE_SLOTS 16
static bool
image_level_slots(struct air_ctx *c, unsigned binding, unsigned *base, unsigned *count)
{
   struct air_shader_info *info = c->info;
   unsigned primary = ~0u, next = 0;
   for (unsigned i = 0; i < info->num_resources; i++) {
      const struct air_resource *r = &info->resources[i];
      if (r->kind != AIR_RESOURCE_IMAGE)
         continue;
      next = MAX2(next, r->image_slot + 1);
      if (r->index == binding && r->image_slot == r->index && primary == ~0u)
         primary = i;
   }
   if (primary == ~0u)
      return air_error(c, "intrinsic: a mip level write to texture %u, which is not an image",
                       binding);
   if (info->resources[primary].level_count) {
      *base = info->resources[primary].level_base;
      *count = info->resources[primary].level_count;
      return true;
   }
   /* Mercury's VariableBlurrer pyramid is 10 levels (414x896): with eight aliases its
    * levels 8 and 9 were written into level 7 (A71, 2026-11-23, pixelated blur). */
   unsigned n = next < AIR_IMAGE_SLOTS ? MIN2(15, AIR_IMAGE_SLOTS - next) : 0;
   if (n < 2)
      return air_error(c, "intrinsic: no image slots left for the mip levels of texture %u",
                       binding);
   info->resources = reralloc(c->mem_ctx, info->resources, struct air_resource,
                              info->num_resources + n);
   for (unsigned k = 0; k < n; k++) {
      struct air_resource *a = &info->resources[info->num_resources + k];
      *a = info->resources[primary];
      a->image_slot = next + k;
      a->mip_level = k;
      a->level_base = a->level_count = 0;
   }
   info->num_resources += n;
   info->resources[primary].level_base = next;
   info->resources[primary].level_count = n;
   *base = next;
   *count = n;
   return true;
}

/* a constant i1/i32 argument, which these intrinsics use as flags */'''),
     ('''      uint64_t lod;
      if (!tex_flag(c, in, arg, &lod))
         return false;
      if (lod != 0)
         return air_error(c, "intrinsic: air.%s to mip level %u (only 0 is handled)",
                          n->part[0], (unsigned)lod);
      if (!tex.is_image)
         return air_error(c, "intrinsic: air.%s to a texture the interface says is not "
                             "written", n->part[0]);
      nir_image_store(&c->b, nir_imm_int(&c->b, tex.binding),''',
      '''      if (!tex.is_image)
         return air_error(c, "intrinsic: air.%s to a texture the interface says is not "
                             "written", n->part[0]);
      /* level 0 by a constant is the texture's own binding; any other level, or one
       * computed at run time, picks the level alias for it (image_level_slots) */
      nir_def *slot = nir_imm_int(&c->b, tex.binding);
      uint64_t lod = 0;
      if (!air_const_uint(in->operands[arg], &lod) || lod != 0) {
         unsigned base, count;
         if (!image_level_slots(c, tex.binding, &base, &count))
            return false;
         nir_def *level = air_get_ssa(c, in->operands[arg]);
         if (!level)
            return false;
         level = nir_umin(&c->b, nir_u2u32(&c->b, level), nir_imm_int(&c->b, count - 1));
         slot = nir_iadd_imm(&c->b, level, base);
      }
      nir_image_store(&c->b, slot,'''),
     ('''      nir_def *value = air_get_ssa(c, in->operands[arg++]);
      if (!value)
         return false;
      if (!tex.is_image)''',
      '''      const struct air_value *stored = in->operands[arg++];
      nir_def *value = air_get_ssa(c, stored);
      if (!value)
         return false;
      /* A texture write returns void; its operand carries the texel type. */
      dest_type = tex_dest_type(c, stored->type, n);
      if (!tex.is_image)'''),
     # A texture or sampler chosen at run time (a pointer phi between them, Mercury), and
     # air.is_null_texture_*: the operation is translated once per place the pointer can
     # name and the results selected; a null side gives the other side's answer, which
     # the shader does not use (it tests is_null first). Writes through such a pointer
     # stay refused.
     ('''      air_set(c, &in->base, air_val_ptr(c, p));
      return true;
   }
   struct air_tex_name t;
''',
      '''      air_set(c, &in->base, air_val_ptr(c, p));
      return true;
   }
   if (!strncmp(n->part[0], "is_null_texture", 15)) {
      nir_def *r = null_texture_test(c, air_get(c, in->operands[1]));
      if (!r)
         return false;
      air_set(c, &in->base, air_val_ssa(c, r));
      return true;
   }
   for (unsigned k = 1; k < in->num_operands; k++) {
      struct hash_entry *he = _mesa_hash_table_search(c->values, in->operands[k]);
      struct air_val *v = he ? he->data : NULL;
      if (!v || v->kind != AIR_VAL_PTR_SELECT || v->num_elems != 2)
         continue;
      if (!strncmp(n->part[0], "write_", 6))
         return air_error(c, "intrinsic: air.%s through a texture chosen at run time",
                          n->part[0]);
      struct air_val *res[2] = { NULL, NULL };
      for (unsigned s = 0; s < 2; s++) {
         struct air_val *el = v->elems[s];
         if (el->kind == AIR_VAL_PTR && el->ptr.class == AIR_PTR_NONE)
            continue;
         _mesa_hash_table_insert(c->values, in->operands[k], el);
         bool ok = texture_op(c, in, n);
         _mesa_hash_table_insert(c->values, in->operands[k], v);
         if (!ok)
            return false;
         struct hash_entry *re = _mesa_hash_table_search(c->values, &in->base);
         res[s] = re ? re->data : NULL;
      }
      if (!res[0] && !res[1])
         return air_error(c, "intrinsic: air.%s of a texture that is null on every path",
                          n->part[0]);
      if (!res[0])
         res[0] = res[1];
      if (!res[1])
         res[1] = res[0];
      struct air_val *r = select_tex_result(c, v->def, res[0], res[1]);
      if (!r)
         return air_error(c, "intrinsic: air.%s through a texture chosen at run time, "
                             "whose result cannot be selected", n->part[0]);
      air_set(c, &in->base, r);
      return true;
   }
   struct air_tex_name t;
'''),
     ('static bool\ntexture_op(struct air_ctx *c, const struct air_inst *in, const struct air_name *n)\n{',
      '''/* is_null_texture on a resolved pointer, or on one chosen at run time */
static nir_def *
null_texture_test(struct air_ctx *c, struct air_val *v)
{
   if (!v) {
      air_error(c, "intrinsic: is_null_texture of nothing");
      return NULL;
   }
   if (v->kind == AIR_VAL_PTR && v->ptr.class == AIR_PTR_NONE)
      return nir_imm_true(&c->b);
   if (v->kind == AIR_VAL_PTR && v->ptr.class == AIR_PTR_TEXTURE && v->ptr.binding < 32) {
      c->info->uses_texture_presence = true;
      nir_def *mask = nir_load_ubo(&c->b, 1, 32, nir_imm_int(&c->b, AIR_TEXTURE_PRESENCE_UBO),
                                   nir_imm_int(&c->b, 0), .align_mul = 4, .range = 4);
      return nir_ieq_imm(&c->b, nir_iand_imm(&c->b, mask, 1u << v->ptr.binding), 0);
   }
   if (v->kind == AIR_VAL_PTR_SELECT && v->num_elems == 2) {
      nir_def *a = null_texture_test(c, v->elems[0]);
      nir_def *b = null_texture_test(c, v->elems[1]);
      return a && b ? nir_bcsel(&c->b, v->def, a, b) : NULL;
   }
   air_error(c, "intrinsic: is_null_texture of something that is not a texture");
   return NULL;
}

/* one of two results of the same operation, member by member for a struct */
static struct air_val *
select_tex_result(struct air_ctx *c, nir_def *cond, struct air_val *a, struct air_val *b)
{
   if (a == b)
      return a;
   if (a->kind == AIR_VAL_SSA && b->kind == AIR_VAL_SSA)
      return air_val_ssa(c, nir_bcsel(&c->b, cond, a->def, b->def));
   if (a->kind == AIR_VAL_AGG && b->kind == AIR_VAL_AGG && a->num_elems == b->num_elems) {
      struct air_val *agg = rzalloc(c->mem_ctx, struct air_val);
      agg->kind = AIR_VAL_AGG;
      agg->num_elems = a->num_elems;
      agg->elems = rzalloc_array(c->mem_ctx, struct air_val *, MAX2(a->num_elems, 1));
      for (unsigned i = 0; i < a->num_elems; i++) {
         agg->elems[i] = select_tex_result(c, cond, a->elems[i], b->elems[i]);
         if (!agg->elems[i])
            return NULL;
      }
      return agg;
   }
   return NULL;
}

static bool
texture_op(struct air_ctx *c, const struct air_inst *in, const struct air_name *n)
{'''),
     ('   if (!strcmp(n.part[0], "get_read_sampler")) {',
      '''   if (!strncmp(n.part[0], "get_function_pointer", 20)) {
      /* no function pointers on this GPU: a null one, which the call through it reads as zero */
      const struct air_type *rt = in->base.type;
      if (rt && rt->kind == AIR_TYPE_POINTER) {
         struct air_ptr none = { .class = AIR_PTR_NONE, .pointee = rt->elem };
         air_set(c, &in->base, air_val_ptr(c, none));
      } else if (rt && rt->kind != AIR_TYPE_VOID) {
         air_set(c, &in->base, air_val_ssa(c, nir_imm_zero(&c->b, air_nir_components(rt),
                                                           air_nir_bit_size(c, rt))));
      }
      return true;
   }
   if (!strcmp(n.part[0], "get_read_sampler")) {'''),
     # air.pack/unpack.unorm.rgb565 (RenderBox resolve shaders)
     (r'''   } else if (!strcmp(op, "unpack") && n->num >= 2 &&
              !strcmp(n->part[1], "unorm4x8")) {''',
      r'''   } else if ((!strcmp(op, "pack") || !strcmp(op, "unpack")) && n->num >= 3 &&
              !strcmp(n->part[1], "unorm") && !strcmp(n->part[2], "rgb565")) {
      /* the same order as rgb10a2 above: component 0 in the low bits, 5/6/5 */
      if (!strcmp(op, "pack")) {
         nir_def *v = nir_fsat(&c->b, nir_f2f32(&c->b, a[0]));
         nir_def *q = nir_f2u32(&c->b, nir_fround_even(&c->b,
                          nir_fmul(&c->b, v, nir_imm_vec3(&c->b, 31.0, 63.0, 31.0))));
         r = nir_ior(&c->b, nir_ior(&c->b, nir_channel(&c->b, q, 0),
                                    nir_ishl_imm(&c->b, nir_channel(&c->b, q, 1), 5)),
                     nir_ishl_imm(&c->b, nir_channel(&c->b, q, 2), 11));
         r = nir_u2uN(&c->b, r, air_nir_bit_size(c, in->base.type));
      } else {
         nir_def *w = nir_u2u32(&c->b, a[0]);
         nir_def *ch[3];
         static const unsigned at[3] = { 0, 5, 11 }, bits[3] = { 5, 6, 5 };
         for (unsigned i = 0; i < 3; i++)
            ch[i] = nir_u2f32(&c->b, nir_ubitfield_extract(&c->b, w, nir_imm_int(&c->b, at[i]),
                                                           nir_imm_int(&c->b, bits[i])));
         r = nir_fmul(&c->b, nir_vec(&c->b, ch, 3),
                      nir_imm_vec3(&c->b, 1.0 / 31.0, 1.0 / 63.0, 1.0 / 31.0));
         if (air_nir_bit_size(c, in->base.type) == 16)
            r = nir_f2f16(&c->b, r);
      }
   } else if (!strcmp(op, "unpack") && n->num >= 2 &&
              !strcmp(n->part[1], "unorm4x8")) {'''),
     # Size of a written texture at a mip level (A71 2026-11-23, wallpaper glass): an image
     # binding is a single-level view of level 0, so nir_image_size ignored the level and
     # Mercury's VariableBlurrer::downsample (uv = (gid + 0.5) / get_width(target, lod))
     # built every level from the top-left corner of the one before: L2..L9 converged to
     # one corner texel (pale, alpha 0). Metal's size at level k is max(1, size0 >> k).
     ('''         return nir_image_size(&c->b, n, 32, index, lod ? lod : nir_imm_int(&c->b, 0),
                               .image_dim = t->dim, .image_array = t->is_array);''',
      '''         nir_def *size0 = nir_image_size(&c->b, n, 32, index, nir_imm_int(&c->b, 0),
                                         .image_dim = t->dim, .image_array = t->is_array);
         if (!lod || (nir_src_is_const(nir_src_for_ssa(lod)) &&
                      nir_src_as_uint(nir_src_for_ssa(lod)) == 0))
            return size0;
         nir_def *ch[4];
         const unsigned dims = n - (t->is_array ? 1 : 0);
         for (unsigned k = 0; k < n; k++) {
            ch[k] = nir_channel(&c->b, size0, k);
            if (k < dims)
               ch[k] = nir_umax(&c->b, nir_ushr(&c->b, ch[k], lod), nir_imm_int(&c->b, 1));
         }
         return nir_vec(&c->b, ch, n);'''))

edit('tools/mesa/air/air_metal.c',
     ('''      out->stream_mask |= 1u << d->buffer_index;
''',
      '''      out->stream_mask |= 1u << d->buffer_index;
      /* VDESC (with /var/local/sweet-native-vblur): what CoreAnimation's variable blur
       * vertex function fetches, attribute by attribute. Its mask coordinate comes from
       * attribute 2 (texcoord1); the scroll-edge blur reads the mask as if that
       * coordinate never left the top (2026-11-24). */
      if (vname && !strncmp(vname, "variable_blur_vert", 18)) {
         static int vdesc = -1;
         static unsigned vdesc_told;
         if (vdesc < 0) {
            FILE *flag = fopen("/var/local/sweet-native-vblur", "r");
            vdesc = flag != NULL;
            if (flag)
               fclose(flag);
         }
         if (vdesc && __atomic_fetch_add(&vdesc_told, 1, __ATOMIC_RELAXED) < 12)
            fprintf(stderr, "SweetNativeMetal: VDESC %s attr %u (%s) loc %u: mtl fmt %u off %u buf %u -> "
                    "pipe %s off %u stride %u vb %u\\n", vname, a->index, a->name ? a->name : "?", loc,
                    d->format, d->offset, d->buffer_index, util_format_short_name(f->pipe),
                    (unsigned)out->element[loc].src_offset, (unsigned)out->element[loc].src_stride,
                    (unsigned)out->element[loc].vertex_buffer_index);
      }
'''),
     ('''   unsigned old_images=device->native_pending_images[stage];
''',
      '''   if (stage == PIPE_SHADER_COMPUTE && strstr(name, "VariableBlurrer::")) {
      static int enabled = -1;
      static unsigned budget;
      int trace = __atomic_load_n(&enabled, __ATOMIC_RELAXED);
      if (trace < 0) {
         FILE *flag = fopen("/var/local/sweet-native-arc-bindings", "r");
         trace = flag != NULL;
         if (flag)
            fclose(flag);
         __atomic_store_n(&enabled, trace, __ATOMIC_RELAXED);
      }
      if (trace && __atomic_fetch_add(&budget, 1, __ATOMIC_RELAXED) < 8) {
         char details[640] = {0};
         size_t used = 0;
         for (unsigned i = 0; i < num_views && used < sizeof(details) - 1; i++) {
            if (views[i]) {
               int n = snprintf(details + used, sizeof(details) - used,
                                " s%u=%p/L%u-%u:%u", i, (void *)views[i]->texture,
                                views[i]->u.tex.first_level, views[i]->u.tex.last_level,
                                views[i]->format);
               if (n > 0)
                  used += MIN2((size_t)n, sizeof(details) - used - 1);
            }
         }
         for (unsigned i = 0; i < num_images && used < sizeof(details) - 1; i++) {
            if (images[i].resource) {
               int n = snprintf(details + used, sizeof(details) - used,
                                " i%u=%p/L%u:%u", i, (void *)images[i].resource,
                                images[i].u.tex.level, images[i].format);
               if (n > 0)
                  used += MIN2((size_t)n, sizeof(details) - used - 1);
            }
         }
         fprintf(stderr, "SweetNativeMetal: ARCBIND %s%s\\n", name, details);
      }
   }
   unsigned old_images=device->native_pending_images[stage];
'''),
     # Mercury draws Space 4x and resolves into its drawable. pipe->blit of a 4x source is
     # refused by the fd6 2D engine and falls back to u_blitter, whose
     # util_blitter_is_blit_supported asks is_format_supported(nr_samples, nr_storage_samples)
     # and fd6 declines MAX2(1, 4) != MAX2(1, 0): the resolve was dropped in silence, and the
     # 828x1792 private resolve stage read 100% zero on the A71 (2026-11-22). Bergamota's
     # A630 port found the same and the wallpaper appeared once storage samples were set.
     # A6XX_TEX_SAMP_1_MIN/MAX_LOD are unsigned 4.8 fixed point (12 bits): Metal's default
     # lodMaxClamp (FLT_MAX, or 65504 in a constexpr sampler word) packs as 0xFFE000 and
     # keeps the low bits, 0, so every sample clamped to level 0. Mercury's blur pyramid was
     # built from level 0 at every level and came out pixelated (A71, 2026-11-23); the same
     # bug was found on iOS 16 (ios-a71 effefe8, max_lod 16.0 wrapped to 0).
     ('      .min_lod = st->lod_min,\n      .max_lod = st->lod_max,\n',
      '      .min_lod = CLAMP(st->lod_min, 0.0f, 15.0f),\n'
      '      .max_lod = CLAMP(st->lod_max, 0.0f, 15.0f),\n'),
     # A shader image of an sRGB texture: freedreno's image (IBO) path has no sRGB store,
     # and Mercury's VariableBlurrer pyramid (BGRA8Unorm_sRGB, 414x896) read back levels
     # 2-8 as near-white with alpha 0 (A71 2026-11-23); the glass element in the
     # wallpaper sampled them. Bound as the linear twin, as Mesa's own frontends do.
     # ...and an sRGB texture a shader writes is stored linear: the image store cannot encode,
     # so with sRGB storage every pyramid level was decoded once more than written and the
     # pyramid darkened to black by level 6 (A71 2026-11-23). Linear storage keeps rendering
     # (no encode), resolves from sRGB (blit decodes), image stores and sampling (no decode)
     # all in linear values. Only for an explicit ShaderWrite usage and never an IOSurface, so
     # CPU uploads of sRGB-encoded images keep their sRGB resource.
     ('      .target = target, .format = fmt->pipe,\n',
      '      .target = target,\n'
      '      .format = (!import && (shape->usage & RWA_USAGE_SHADER_WRITE) &&\n'
      '                 util_format_is_srgb(fmt->pipe)) ? util_format_linear(fmt->pipe) : fmt->pipe,\n'),
     ('            .resource = t->res,\n            .format = t->res->format,\n',
      '            .resource = t->res,\n'
      '            .format = util_format_linear(t->res->format),\n'),
     # MTLTextureSwizzleChannels. CoreAnimation views an opaque layer's IOSurface with
     # alpha -> one; the swizzle was dropped, and backboardd's source-over pass over
     # Mercury's wallpaper added it to itself (twice as bright, A71 2026-11-23).
     ('   bool shader_read, shader_write;\n};\n',
      '   bool shader_read, shader_write;\n'
      '   unsigned char mtl_swizzle[4];    /* MTLTextureSwizzle r, g, b, a; all 0 = none set */\n'
      '};\n'),
     ('            t->view = pipe->create_sampler_view(pipe, t->res, &tmpl);\n',
      '''            if (t->mtl_swizzle[0] | t->mtl_swizzle[1] | t->mtl_swizzle[2] | t->mtl_swizzle[3]) {
               /* MTLTextureSwizzle: 0 zero, 1 one, 2 red .. 5 alpha, composed over the
                * format's own default swizzle */
               const unsigned char base[4] = { tmpl.swizzle_r, tmpl.swizzle_g, tmpl.swizzle_b,
                                               tmpl.swizzle_a };
               unsigned char out[4];
               for (unsigned k = 0; k < 4; k++) {
                  const unsigned m = t->mtl_swizzle[k];
                  out[k] = m == 0 ? PIPE_SWIZZLE_0 : m == 1 ? PIPE_SWIZZLE_1 :
                           m <= 5 ? base[m - 2] : base[k];
               }
               tmpl.swizzle_r = out[0];
               tmpl.swizzle_g = out[1];
               tmpl.swizzle_b = out[2];
               tmpl.swizzle_a = out[3];
            }
            t->view = pipe->create_sampler_view(pipe, t->res, &tmpl);
'''),
     ('int\nrwa_texture_write(struct rwa_texture *texture, unsigned level, unsigned layer,',
      '''/* A Metal texture swizzle (newTextureViewWithPixelFormat:...swizzle:, or a
 * descriptor's swizzle): kept with the texture and applied to its sampler view. */
int rwa_texture_set_swizzle(struct rwa_texture *texture, const unsigned char swizzle[4]);
int
rwa_texture_set_swizzle(struct rwa_texture *texture, const unsigned char swizzle[4])
{
   if (!texture)
      return -1;
   const bool identity = swizzle[0] == 2 && swizzle[1] == 3 && swizzle[2] == 4 && swizzle[3] == 5;
   for (unsigned k = 0; k < 4; k++)
      texture->mtl_swizzle[k] = identity ? 0 : swizzle[k];
   pipe_sampler_view_reference(&texture->view, NULL);
   return 0;
}

int
rwa_texture_write(struct rwa_texture *texture, unsigned level, unsigned layer,'''),
     ('.array_size = array_size, .last_level = mips - 1, .nr_samples = query_samples,\n',
      '.array_size = array_size, .last_level = mips - 1, .nr_samples = query_samples,\n'
      '      .nr_storage_samples = query_samples,\n'),
     ('   unsigned num_views = 0, num_images = 0, num_samplers = 0;\n',
      '   unsigned num_views = 0, num_images = 0, num_samplers = 0;\n'
      '   uint32_t texture_presence = 0;\n'),
     ('''      switch (r->kind) {
      case AIR_RESOURCE_DEVICE_BUFFER:
         if (r->index >= ARRAY_SIZE(sb)) {''',
      '''      if (t && r->index < 32 &&
          (r->kind == AIR_RESOURCE_TEXTURE || r->kind == AIR_RESOURCE_IMAGE))
         texture_presence |= 1u << r->index;
      switch (r->kind) {
      case AIR_RESOURCE_DEVICE_BUFFER:
         if (r->index >= ARRAY_SIZE(sb)) {'''),
     ('''   if (num_ssbo)
      pipe->set_shader_buffers(pipe, stage, 0, num_ssbo, sb, writable);''',
      '''   if (info->uses_texture_presence) {
      struct pipe_constant_buffer cb = { .buffer_size = sizeof(texture_presence) };
      u_upload_data(pipe->stream_uploader, 0, sizeof(texture_presence), 64, &texture_presence,
                    &cb.buffer_offset, &cb.buffer);
      if (!cb.buffer) {
         say(why, why_size, "%s: could not upload the texture-presence mask", name);
         return -1;
      }
      native_bind_constant(device, stage, AIR_TEXTURE_PRESENCE_UBO, &cb);
      pipe_resource_reference(&cb.buffer, NULL);
   }
   if (num_ssbo)
      pipe->set_shader_buffers(pipe, stage, 0, num_ssbo, sb, writable);'''),
     ('#include "nir_builder.h"\n',
      '#include "nir_builder.h"\n#include "nir_serialize.h"\n#include "util/blob.h"\n'),
     (' * What is deliberately absent is everything packed into a 32-bit word -- RGB10A2Unorm,\n',
      ' * BGR10A2Unorm uses the documented low-to-high B, G, R, A layout. Other packed\n'
      ' * 32-bit formats are deliberately absent here -- RGB10A2Unorm,\n'),
     ('   {  81, "MTLPixelFormatBGRA8Unorm_sRGB", PIPE_FORMAT_B8G8R8A8_SRGB },\n',
      '   {  81, "MTLPixelFormatBGRA8Unorm_sRGB", PIPE_FORMAT_B8G8R8A8_SRGB },\n'
      '   {  94, "MTLPixelFormatBGR10A2Unorm",   PIPE_FORMAT_B10G10R10A2_UNORM },\n'),
     ('   if (f >= 90 && f <= 94)\n'
      '      return "one of Metal\'s formats packed into a 32-bit word (RGB10A2, RG11B10, RGB9E5, "\n'
      '             "BGR10A2), whose field order and bias this library will not guess: an error of "\n',
      '   if (f >= 90 && f <= 93)\n'
      '      return "one of Metal\'s formats packed into a 32-bit word (RGB10A2, RG11B10, RGB9E5), "\n'
      '             "whose field order and bias this library will not guess: an error of "\n'),
     ('struct rwa_device {\n',
      '''/* Keep recent compiled variants across pipeline lifetimes on the same context. */
#define RWA_COMPUTE_CACHE_SIZE 8
#define RWA_COMPUTE_CACHE_KEY_LIMIT (2u * 1024u * 1024u)

struct rwa_compute_variant {
   void *cso;
   unsigned refs;
   size_t key_size;
   void *key;
};

struct rwa_device {
   struct rwa_compute_variant *compute_cache[RWA_COMPUTE_CACHE_SIZE];
   unsigned compute_cache_next;
   bool compute_cache_reported;
'''),
     ('''   /* One compiled state, not a cache. The threadgroup size is a dispatch argument in
    * Metal and a shader constant to both Gallium drivers here, so the state belongs to
    * a size; a caller that alternates two sizes recompiles each time, which is a cost
    * no caller here pays and cheaper than an eviction policy a library cannot choose.
    */
   void *cso;
''',
      '''   /* The pipeline retains its most recently used variant, even if evicted. */
   struct rwa_compute_variant *variant;
'''),
     ('void\nrwa_device_close(struct rwa_device *device)\n',
      '''static void release_compute_variant(struct rwa_device *, struct rwa_compute_variant *);

void
rwa_device_close(struct rwa_device *device)
'''),
     ('''   device->pipe->destroy(device->pipe);
   device->screen->destroy(device->screen);
   free(device);
   glsl_type_singleton_decref();
}
''',
      '''   for (unsigned i = 0; i < RWA_COMPUTE_CACHE_SIZE; i++)
      release_compute_variant(device, device->compute_cache[i]);
   device->pipe->destroy(device->pipe);
   device->screen->destroy(device->screen);
   free(device);
   glsl_type_singleton_decref();
}
'''),
     ('void\nrwa_compute_destroy(struct rwa_compute *compute)\n',
      '''static void
release_compute_variant(struct rwa_device *device, struct rwa_compute_variant *variant)
{
   if (variant && --variant->refs == 0) {
      delete_compute_state(device, variant->cso);
      free(variant->key);
      free(variant);
   }
}

void
rwa_compute_destroy(struct rwa_compute *compute)
'''),
     ('''   if (compute->cso)
      delete_compute_state(compute->device, compute->cso);
''',
      '''   release_compute_variant(compute->device, compute->variant);
'''),
     ('''   if (compute->cso && compute->cso_block[0] == block[0] &&
       compute->cso_block[1] == block[1] && compute->cso_block[2] == block[2])
      return compute->cso;

   if (compute->cso) {
      delete_compute_state(device, compute->cso);
      compute->cso = NULL;
   }
''',
      '''   if (compute->variant && compute->cso_block[0] == block[0] &&
       compute->cso_block[1] == block[1] && compute->cso_block[2] == block[2])
      return compute->variant->cso;
'''),
     ('''   if (!finalize_for_gallium(cs, device->screen, why, why_size)) {ralloc_free(cs);return NULL;}
''',
      '''   /* This NIR already includes the function constants and the group size. Strip
    * names and compare the full serialization within this device's context.
    */
   struct blob key;
   blob_init(&key);
   nir_serialize(&key, cs, true);
   const bool cacheable = !key.out_of_memory && key.size <= RWA_COMPUTE_CACHE_KEY_LIMIT;
   if (cacheable) {
      for (unsigned i = 0; i < RWA_COMPUTE_CACHE_SIZE; i++) {
         struct rwa_compute_variant *variant = device->compute_cache[i];
         if (!variant || variant->key_size != key.size ||
             memcmp(variant->key, key.data, key.size) != 0)
            continue;

         blob_finish(&key);
         ralloc_free(cs);
         variant->refs++;
         release_compute_variant(device, compute->variant);
         compute->variant = variant;
         memcpy(compute->cso_block, block, sizeof(compute->cso_block));
         if (!device->compute_cache_reported) {
            fprintf(stderr, "SweetNativeMetal: reusing compiled compute variant %s (%ux%ux%u)\\n",
                    compute->info.entry_point ? compute->info.entry_point : "unknown",
                    block[0], block[1], block[2]);
            device->compute_cache_reported = true;
         }
         return variant->cso;
      }
   }

   if (!finalize_for_gallium(cs, device->screen, why, why_size)) {
      blob_finish(&key);
      ralloc_free(cs);
      return NULL;
   }
'''),
     ('''      say(why, why_size, "%s would not make a compute pipeline of %s",
''',
      '''      blob_finish(&key);
      say(why, why_size, "%s would not make a compute pipeline of %s",
'''),
     ('''         delete_compute_state(device, cso);
         return NULL;
''',
      '''         delete_compute_state(device, cso);
         blob_finish(&key);
         return NULL;
'''),
     ('''   compute->cso = cso;
   compute->cso_block[0] = block[0];
   compute->cso_block[1] = block[1];
   compute->cso_block[2] = block[2];
''',
      '''   struct rwa_compute_variant *variant = calloc(1, sizeof(*variant));
   if (!variant) {
      delete_compute_state(device, cso);
      blob_finish(&key);
      say(why, why_size, "out of memory keeping a compiled compute variant");
      return NULL;
   }
   variant->cso = cso;
   variant->refs = 1;
   if (cacheable) {
      variant->key = key.data;
      variant->key_size = key.size;
      variant->refs++;
      unsigned index = device->compute_cache_next;
      release_compute_variant(device, device->compute_cache[index]);
      device->compute_cache[index] = variant;
      device->compute_cache_next = (index + 1) % RWA_COMPUTE_CACHE_SIZE;
   } else {
      blob_finish(&key);
   }
   release_compute_variant(device, compute->variant);
   compute->variant = variant;
   memcpy(compute->cso_block, block, sizeof(compute->cso_block));
'''),
     ('         images[r->index] = (struct pipe_image_view){',
      '         images[r->image_slot] = (struct pipe_image_view){'),
     ('            .u.tex.level = t->first_level,\n            .u.tex.first_layer = 0,',
      '''            /* a level alias past the texture's levels repeats its last one: the shader
             * clamps to the aliases there are, not to the levels this texture has */
            .u.tex.level = t->first_level + MIN2(r->mip_level, t->level_count - 1),
            .u.tex.first_layer = 0,'''),
     ('         num_images = MAX2(num_images, r->index + 1);',
      '         num_images = MAX2(num_images, r->image_slot + 1);'),
     # VideoToolbox's VTMTSComputeFunction1x1 (Mercury) writes a CVMetalTextureCache texture of
     # an IOSurface that was made without MTLTextureUsageShaderWrite; Apple's driver does not
     # enforce the usage there. An imported surface is offered as writable when the GPU can bind
     # its format as an image.
     ('''   if (depth_stencil)
      write = false;
''',
      '''   if (depth_stencil)
      write = false;
   if (import && !write && !multisample && !depth_stencil &&
       device->screen->is_format_supported(device->screen, fmt->pipe, target, 0, 0,
                                           PIPE_BIND_SHADER_IMAGE))
      write = true;
'''),
     ('   struct pipe_surface *native_surface;\n',
      '   struct pipe_surface *native_surface;\n'
      '   struct pipe_resource *resolve_stage; /* Single-sample intermediate for external resolves. */\n'),
     ('   pipe_surface_reference(&texture->native_surface, NULL);\n',
      '   pipe_surface_reference(&texture->native_surface, NULL);\n'
      '   pipe_resource_reference(&texture->resolve_stage, NULL);\n'),
     # ASTC (Mercury's albedo-a.ktx is astc_6x6_srgb); the A618 samples ASTC LDR itself
     ('#include "util/u_inlines.h"\n',
      '#include "util/u_inlines.h"\n#include "util/u_gen_mipmap.h"\n'),
     ('int\nrwa_texture_write(struct rwa_texture *texture, unsigned level, unsigned layer,',
      '''/* -generateMipmapsForTexture: -- every level after the first from the one before, by the
 * GPU, through Gallium's own helper (a blit per level with a linear filter). */
int rwa_texture_generate_mipmap(struct rwa_texture *texture);
int
rwa_texture_generate_mipmap(struct rwa_texture *texture)
{
   if (!texture || texture->level_count < 2)
      return 0;
   struct pipe_resource *res = texture->res;
   unsigned last_layer = (res->target == PIPE_TEXTURE_3D ? u_minify(res->depth0, texture->first_level)
                                                          : res->array_size) - 1;
   return util_gen_mipmap(texture->device->pipe, res, res->format, texture->first_level,
                          texture->first_level + texture->level_count - 1, 0, last_layer,
                          PIPE_TEX_FILTER_LINEAR) ? 0 : -1;
}

/* A colour attachment's resolveTexture (MTLStoreActionMultisampleResolve): the attachment
 * blitted into level `level`, slice `slice` of the other texture, by the GPU in order with
 * the pass. A Gallium blit from a multisample resource is the resolve; from a one-sample one
 * it is a copy, which is what Metal's resolve of a one-sample attachment amounts to. Mercury
 * draws its wallpaper this way and the resolve texture stayed black. */
int rwa_texture_resolve(struct rwa_texture *src, struct rwa_texture *dst, unsigned level,
                        unsigned slice, bool external, unsigned trace_seq);
int
rwa_texture_resolve(struct rwa_texture *src, struct rwa_texture *dst, unsigned level,
                    unsigned slice, bool external, unsigned trace_seq)
{
   if (!src || !dst)
      return -1;
   unsigned sl = src->first_level, dl = dst->first_level + level;
   int w = (int)MIN2(u_minify(src->res->width0, sl), u_minify(dst->res->width0, dl));
   int h = (int)MIN2(u_minify(src->res->height0, sl), u_minify(dst->res->height0, dl));
   struct pipe_blit_info b = { 0 };
   b.src.resource = src->res;
   b.src.level = sl;
   b.src.format = src->res->format;
   b.src.box = (struct pipe_box){ .x = 0, .y = 0, .z = 0, .width = w, .height = h, .depth = 1 };
   b.dst.resource = dst->res;
   b.dst.level = dl;
   b.dst.format = dst->res->format;
   b.dst.box = (struct pipe_box){ .x = 0, .y = 0, .z = (int)slice, .width = w, .height = h,
                                  .depth = 1 };
   b.mask = PIPE_MASK_RGBA;
   b.filter = PIPE_TEX_FILTER_NEAREST;
   struct pipe_context *pipe = dst->device->pipe;
   if (external && src->res->nr_samples > 1 && dst->res->nr_samples <= 1 &&
       src->res->format == dst->res->format && dst->res->target == PIPE_TEXTURE_2D) {
      /* A618 produced color in private resolves and transparent IOSurface output.
       * Resolve away from the imported layout, then copy the single-sample texels. */
      struct pipe_resource *stage = src->resolve_stage;
      if (!stage || stage->width0 != (unsigned)w || stage->height0 != (unsigned)h) {
         struct pipe_resource desc = {
            .target = PIPE_TEXTURE_2D, .format = dst->res->format,
            .width0 = w, .height0 = h, .depth0 = 1, .array_size = 1,
            .bind = PIPE_BIND_RENDER_TARGET | PIPE_BIND_SAMPLER_VIEW,
            .usage = PIPE_USAGE_DEFAULT,
         };
         stage = pipe->screen->resource_create(pipe->screen, &desc);
         if (!stage)
            return -1;
         pipe_resource_reference(&src->resolve_stage, NULL);
         src->resolve_stage = stage;
      }
      b.dst.resource = stage;
      b.dst.level = 0;
      b.dst.box.z = 0;
      pipe->blit(pipe, &b);
      if (trace_seq && (stage->format == PIPE_FORMAT_B8G8R8A8_UNORM ||
                        stage->format == PIPE_FORMAT_B8G8R8A8_SRGB)) {
         struct pipe_transfer *transfer = NULL;
         const uint8_t *map = pipe->texture_map(pipe, stage, 0, PIPE_MAP_READ, &b.dst.box, &transfer);
         if (map) {
            unsigned sum[4] = { 0 }, transparent = 0;
            for (unsigned y = 0; y < 16; y++) {
               const uint8_t *row = map + (size_t)(2 * y + 1) * h / 32 * transfer->stride;
               for (unsigned x = 0; x < 16; x++) {
                  const uint8_t *pixel = row + ((2 * x + 1) * w / 32) * 4;
                  for (unsigned i = 0; i < 4; i++)
                     sum[i] += pixel[i];
                  transparent += pixel[3] == 0;
               }
            }
            fprintf(stderr, "SweetNativeMetal: TEXSTAT %u private resolve stage %dx%d mean %u,%u,%u,%u clear %u%%\\n",
                    trace_seq, w, h, sum[0] / 256, sum[1] / 256, sum[2] / 256, sum[3] / 256,
                    transparent * 100 / 256);
            pipe->texture_unmap(pipe, transfer);
         } else {
            fprintf(stderr, "SweetNativeMetal: TEXSTAT %u could not read the private resolve stage\\n", trace_seq);
         }
      }
      /* backboardd composites Mercury's drawable source-over; Mercury's resolve came out
       * 39% alpha 0 on the A71 (2026-11-22) and the wallpaper was added to what lay
       * under it (twice as bright). /var/local/sweet-mtl-opaque-resolve lists the
       * processes ("*" = all) whose external resolves are written with alpha 1. */
      static int opaque = -1;
      if (opaque < 0) {
         opaque = 0;
         FILE *f = fopen("/var/local/sweet-mtl-opaque-resolve", "r");
         if (f) {
            char list[256] = { 0 };
            size_t n = fread(list, 1, sizeof(list) - 1, f);
            fclose(f);
            list[n] = 0;
#if defined(__APPLE__)
            const char *me = getprogname();
#else
            const char *me = NULL;
#endif
            opaque = strchr(list, '*') != NULL || (me && *me && strstr(list, me) != NULL);
         }
         fprintf(stderr, "SweetNativeMetal: external resolves %s (/var/local/sweet-mtl-opaque-resolve)\\n",
                 opaque ? "written with alpha 1" : "copied as rendered");
      }
      if (opaque) {
         struct pipe_blit_info o = { 0 };
         o.src.resource = stage;
         o.src.level = 0;
         o.src.format = stage->format;
         o.src.box = (struct pipe_box){ .x = 0, .y = 0, .z = 0, .width = w, .height = h, .depth = 1 };
         o.dst.resource = dst->res;
         o.dst.level = dl;
         o.dst.format = dst->res->format;
         o.dst.box = (struct pipe_box){ .x = 0, .y = 0, .z = (int)slice, .width = w, .height = h,
                                        .depth = 1 };
         /* freedreno's fd_blitter_blit makes its own identity-swizzle source view, so a
          * blit swizzle of A = 1 was dropped (2026-11-23). Instead: the destination is
          * cleared to opaque black, then only R, G and B are blitted over it (u_blitter
          * honours the mask as a colour write mask). backboardd draws this surface twice
          * (an opaque copy, then source-over), which doubled any pixel with alpha < 1. */
         struct pipe_surface st = { 0 };
         st.format = dst->res->format;
         st.u.tex.level = dl;
         st.u.tex.first_layer = st.u.tex.last_layer = slice;
         struct pipe_surface *surf = pipe->create_surface(pipe, dst->res, &st);
         if (surf) {
            union pipe_color_union black = { .f = { 0.0f, 0.0f, 0.0f, 1.0f } };
            pipe->clear_render_target(pipe, surf, &black, 0, 0, (unsigned)w, (unsigned)h, false);
            pipe_surface_reference(&surf, NULL);
            o.mask = PIPE_MASK_R | PIPE_MASK_G | PIPE_MASK_B;
         } else {
            o.mask = PIPE_MASK_RGBA;
         }
         o.filter = PIPE_TEX_FILTER_NEAREST;
         pipe->blit(pipe, &o);
         return 0;
      }
      pipe->resource_copy_region(pipe, dst->res, dl, 0, 0, slice, stage, 0, &b.dst.box);
      return 0;
   }
   pipe->blit(pipe, &b);
   return 0;
}

int
rwa_texture_write(struct rwa_texture *texture, unsigned level, unsigned layer,'''),
     ('   {  62, "MTLPixelFormatRG16Snorm",       PIPE_FORMAT_R16G16_SNORM },\n',
      '   {  62, "MTLPixelFormatRG16Snorm",       PIPE_FORMAT_R16G16_SNORM },\n' + ASTC_ROWS),
     # a caller's rows of a block format are rows of blocks: counted in blocks, which is the
     # same number as before for every uncompressed format
     ('   size_t least = (size_t)box->width * texel;',
      '   size_t least = (size_t)util_format_get_nblocksx(texture->res->format, box->width) * texel;'),
     ('                                          PIPE_MAP_WRITE, &box, bytes, row,\n'
      '                                          row * box.height);',
      '                                          PIPE_MAP_WRITE, &box, bytes, row,\n'
      '                                          row * util_format_get_nblocksy(texture->res->format,\n'
      '                                                                         box.height));'),
     # A draw that samples the texture it renders into. CoreAnimation's variable blur
     # builds its mip chain in place: variable_blur_downsample renders level k+1 of a
     # texture while sampling the same texture (draw trace 2026-11-20, #c298). Metal
     # allows it; the Adreno gives no ordering between a render target and a texture
     # fetch of the same memory inside a pass, and the glass came and went. Such a draw
     # samples a copy instead, made by the GPU just before it.
     ('   struct pipe_screen *screen;\n   struct pipe_context *pipe;\n',
      '   struct pipe_screen *screen;\n   struct pipe_context *pipe;\n'
      '   /* the colour targets of the draw being bound, for hazard_view */\n'
      '   struct pipe_resource *hazard_targets[8];\n'
      '   unsigned hazard_count;\n'),
     ('   struct pipe_sampler_view *view;  /* made when a dispatch first samples it, then kept */\n',
      '   struct pipe_sampler_view *view;  /* made when a dispatch first samples it, then kept */\n'
      '   struct pipe_resource *hazard_res;       /* a copy for draws that render into this */\n'
      '   struct pipe_sampler_view *hazard_view;\n'),
     ('   pipe_sampler_view_reference(&texture->view, NULL);\n   pipe_surface_reference(&texture->native_surface, NULL);',
      '   pipe_sampler_view_reference(&texture->view, NULL);\n'
      '   pipe_sampler_view_reference(&texture->hazard_view, NULL);\n'
      '   pipe_resource_reference(&texture->hazard_res, NULL);\n'
      '   pipe_surface_reference(&texture->native_surface, NULL);'),
     ('static int\nbind_stage(struct rwa_device *device, enum pipe_shader_type stage,',
      '''/* The view a draw samples when the texture is also one of its colour targets: a copy of
 * every level of it, made by the GPU in submission order before the draw, kept with the
 * texture and refreshed at each such draw. NULL if the copy could not be made.
 */
static struct pipe_sampler_view *
hazard_view(struct rwa_device *device, struct rwa_texture *t)
{
   struct pipe_context *pipe = device->pipe;
   struct pipe_resource *res = t->res;
   if (!t->hazard_res) {
      struct pipe_resource tmpl = { 0 };
      tmpl.target = res->target;
      tmpl.format = res->format;
      tmpl.width0 = res->width0;
      tmpl.height0 = res->height0;
      tmpl.depth0 = res->depth0;
      tmpl.array_size = res->array_size;
      tmpl.last_level = res->last_level;
      tmpl.nr_samples = res->nr_samples;
      tmpl.nr_storage_samples = res->nr_storage_samples;
      tmpl.usage = PIPE_USAGE_DEFAULT;
      tmpl.bind = PIPE_BIND_SAMPLER_VIEW;
      t->hazard_res = device->screen->resource_create(device->screen, &tmpl);
      if (!t->hazard_res)
         return NULL;
      struct pipe_sampler_view v = { 0 };
      u_sampler_view_default_template(&v, t->hazard_res, t->hazard_res->format);
      if (res->target == PIPE_TEXTURE_2D) {
         v.u.tex.first_level = t->first_level;
         v.u.tex.last_level = t->first_level + t->level_count - 1;
      }
      t->hazard_view = pipe->create_sampler_view(pipe, t->hazard_res, &v);
      if (!t->hazard_view) {
         pipe_resource_reference(&t->hazard_res, NULL);
         return NULL;
      }
   }
   for (unsigned l = t->first_level; l < t->first_level + t->level_count; l++) {
      struct pipe_box box = {
         .x = 0, .y = 0, .z = 0,
         .width = (int)u_minify(res->width0, l),
         .height = (int)u_minify(res->height0, l),
         .depth = res->target == PIPE_TEXTURE_3D ? (int)u_minify(res->depth0, l)
                                                  : (int)res->array_size,
      };
      pipe->resource_copy_region(pipe, t->hazard_res, l, 0, 0, 0, res, l, &box);
   }
   static unsigned logged;
   if (logged < 4) {
      logged++;
      fprintf(stderr, "SweetNativeMetal: a draw samples its own colour target (%ux%u, %u levels): "
              "it reads a copy made just before it\\n", res->width0, res->height0, t->level_count);
   }
   return t->hazard_view;
}

static int
bind_stage(struct rwa_device *device, enum pipe_shader_type stage,'''),
     ('         views[r->index] = t->view;\n',
      '''         {
            struct pipe_sampler_view *use = t->view;
            for (unsigned h = 0; h < device->hazard_count; h++) {
               if (device->hazard_targets[h] == t->res) {
                  use = hazard_view(device, t);
                  break;
               }
            }
            if (!use) {
               say(why, why_size, "%s would not copy the %s bound at texture %u, which this "
                                  "draw also renders into", rwa_device_name(device),
                   t->format_name, r->index);
               return -1;
            }
            views[r->index] = use;
         }
'''),
     ('   native_draw_checkpoint(device,&native_phase_at,1);\n',
      '''   native_draw_checkpoint(device,&native_phase_at,1);
   device->hazard_count = 0;
   for (unsigned i = 0; i < draw->color_count && i < 8; i++)
      if (draw->color && draw->color[i])
         device->hazard_targets[device->hazard_count++] = draw->color[i]->res;
'''),
     ('unbind:\n   native_draw_checkpoint(device,&native_phase_at,3);\n',
      'unbind:\n   native_draw_checkpoint(device,&native_phase_at,3);\n   device->hazard_count = 0;\n'),
     # an unbound texture a shader declares but does not read: a zero texel, not a failed command buffer
     (r'''   void *default_sampler;
''',
      r'''   void *default_sampler;
   /* the view an unbound texture slot reads: one zero texel (see null_texture_view) */
   struct pipe_resource *null_texture;
   struct pipe_sampler_view *null_texture_view;
'''),
     # an unbound texture a shader declares but does not read: a zero texel, not a failed command buffer
     (r'''   return device->default_sampler;
}
''',
      r'''   return device->default_sampler;
}

/*
 * A shader that DECLARES a texture it does not read on this path, and an application that
 * therefore binds nothing there, is legal Metal: RenderBox's uber_fragment declares texture 0
 * for every draw and binds one only when its state says it samples. Refusing the draw made
 * the whole command buffer fail ("command buffer error" in Mercury), so the clock and the
 * wallpaper never reached the screen. The slot gets one transparent black texel instead,
 * which is also what a read would return on hardware that tolerates an empty slot.
 */
static struct pipe_sampler_view *
null_texture_view(struct rwa_device *device)
{
   if (!device->null_texture_view) {
      struct pipe_resource tmpl = {
         .target = PIPE_TEXTURE_2D, .format = PIPE_FORMAT_R8G8B8A8_UNORM,
         .width0 = 1, .height0 = 1, .depth0 = 1, .array_size = 1,
         .bind = PIPE_BIND_SAMPLER_VIEW, .usage = PIPE_USAGE_DEFAULT,
      };
      device->null_texture = device->screen->resource_create(device->screen, &tmpl);
      if (!device->null_texture)
         return NULL;
      static const uint8_t zero[4];
      struct pipe_box box = { .width = 1, .height = 1, .depth = 1 };
      device->pipe->texture_subdata(device->pipe, device->null_texture, 0, 0, &box, zero, 4, 4);
      struct pipe_sampler_view vt;
      u_sampler_view_default_template(&vt, device->null_texture, device->null_texture->format);
      device->null_texture_view = device->pipe->create_sampler_view(device->pipe,
                                                                    device->null_texture, &vt);
   }
   return device->null_texture_view;
}
'''),
     # an unbound texture a shader declares but does not read: a zero texel, not a failed command buffer
     (r'''         if (!member && (r->index >= bindings->texture_count ||
                         !bindings->textures[r->index])) {
            say(why, why_size,''',
      r'''         if (!member && !stored && (r->index >= bindings->texture_count ||
                                    !bindings->textures[r->index])) {
            static unsigned told;
            if (told++ < 8)
               fprintf(stderr, "SweetNativeMetal: %s reads texture %u and nothing is bound "
                               "there: a zero texel is bound instead\n", name, r->index);
            break;
         }
         if (!member && (r->index >= bindings->texture_count ||
                         !bindings->textures[r->index])) {
            say(why, why_size,'''),
     # an unbound texture a shader declares but does not read: a zero texel, not a failed command buffer
     (r'''         case AIR_RESOURCE_TEXTURE:
         case AIR_RESOURCE_IMAGE:
            t = bindings->textures[r->index];
            break;''',
      r'''         case AIR_RESOURCE_TEXTURE:
         case AIR_RESOURCE_IMAGE:
            t = r->index < bindings->texture_count ? bindings->textures[r->index] : NULL;
            break;'''),
     # an unbound texture a shader declares but does not read: a zero texel, not a failed command buffer
     (r'''      case AIR_RESOURCE_TEXTURE:
         /* The view is made once and kept with the texture: a device has one context,''',
      r'''      case AIR_RESOURCE_TEXTURE:
         if (!t) {
            /* declared, unbound and not read on this path (check_bindings let it through) */
            views[r->index] = null_texture_view(device);
            if (!views[r->index]) {
               say(why, why_size, "%s would not make the zero texture for unbound texture %u",
                   rwa_device_name(device), r->index);
               return -1;
            }
            num_views = MAX2(num_views, r->index + 1);
            break;
         }
         /* The view is made once and kept with the texture: a device has one context,'''),
     # Cull mode, winding and fill mode per draw (rwa_draw.native_cull/_winding/_fill were
     # declared and never read). The frontend refused them by failing the whole command
     # buffer without a word, which is why Mercury's Space poster encoded every frame
     # (trace 2026-11-22: compute + 3 draws + compute + 4 draws) and committed status 5.
     ('   void *blend, *dsa, *rast, *velem;\n',
      '   void *blend, *dsa, *rast, *velem;\n'
      '   struct pipe_rasterizer_state rast_state; /* what rast was made from */\n'
      '   void *rast_var[12];   /* (cull 0..2 * 2 + Metal winding) * 2 + wireframe */\n'),
     ('   render->rast = device->pipe->create_rasterizer_state(device->pipe,\n      &(struct pipe_rasterizer_state){\n',
      '   render->rast_state = (struct pipe_rasterizer_state){\n'),
     ('         .multisample = samples > 1 });\n',
      '         .multisample = samples > 1 };\n'
      '   render->rast = device->pipe->create_rasterizer_state(device->pipe, &render->rast_state);\n'),
     ('   if (render->rast) {\n      pipe->bind_rasterizer_state(pipe, NULL);\n      pipe->delete_rasterizer_state(pipe, render->rast);\n   }\n',
      '   if (render->rast) {\n      pipe->bind_rasterizer_state(pipe, NULL);\n      pipe->delete_rasterizer_state(pipe, render->rast);\n   }\n'
      '   for (unsigned k = 0; k < ARRAY_SIZE(render->rast_var); k++)\n'
      '      if (render->rast_var[k])\n'
      '         pipe->delete_rasterizer_state(pipe, render->rast_var[k]);\n'),
     ('   pipe->bind_rasterizer_state(pipe, render->rast);\n',
      r'''   void *rast = render->rast;
   {
      /* /var/local/sweet-mtl-cull: "none" draws both faces, "flip" inverts the winding
       * mapping below; read once per process, for checking the mapping on the phone. */
      static int policy = -1;
      int p = __atomic_load_n(&policy, __ATOMIC_RELAXED);
      if (p < 0) {
         char word[16] = { 0 };
         FILE *f = fopen("/var/local/sweet-mtl-cull", "r");
         p = 0;
         if (f) {
            if (fscanf(f, "%15s", word) == 1)
               p = !strcmp(word, "none") ? 1 : !strcmp(word, "flip") ? 2 : 0;
            /* optional process names after the word: the policy applies to those only */
            char who[64];
            bool listed = false, any = false;
            while (fscanf(f, "%63s", who) == 1) {
               any = true;
#if defined(__APPLE__)
               listed |= !strcmp(who, getprogname());
#endif
            }
            if (any && !listed)
               p = 0;
            fclose(f);
         }
         __atomic_store_n(&policy, p, __ATOMIC_RELAXED);
         if (p)
            fprintf(stderr, "SweetNativeMetal: /var/local/sweet-mtl-cull: %s\n",
                    p == 1 ? "culling ignored" : "winding flipped");
      }
      unsigned cull = draw->native_cull <= 2 && p != 1 ? draw->native_cull : 0;
      unsigned winding = (draw->native_winding ? 1 : 0) ^ (p == 2);
      unsigned fill = draw->native_fill ? 1 : 0;
      if (cull || fill) {
         unsigned k = (cull * 2 + winding) * 2 + fill;
         if (!render->rast_var[k]) {
            struct pipe_rasterizer_state s = render->rast_state;
            s.cull_face = cull == 1 ? PIPE_FACE_FRONT : cull == 2 ? PIPE_FACE_BACK : PIPE_FACE_NONE;
            /* Marble's mirrored CoreAnimation layers on A618 confirm that Metal clockwise
             * (0) maps to Gallium front_ccw = 0 on this path. */
            s.front_ccw = winding ? 1 : 0;
            s.fill_front = s.fill_back = fill ? PIPE_POLYGON_MODE_LINE : PIPE_POLYGON_MODE_FILL;
            render->rast_var[k] = pipe->create_rasterizer_state(pipe, &s);
            fprintf(stderr, "SweetNativeMetal: rasterizer variant cull %u winding %u fill %u -> front_ccw %u: %p\n",
                    cull, winding, fill, s.front_ccw, render->rast_var[k]);
         }
         if (render->rast_var[k])
            rast = render->rast_var[k];
      }
   }
   pipe->bind_rasterizer_state(pipe, rast);
'''),
     # filter::bicubic in a shader's own sampler (Mercury Space, 2026-11-22: it failed every
     # command buffer once culling worked). Adreno and Gallium have no bicubic; sample it as
     # linear, as air_run already does, and say so once.
     ('''   if (a->mag_filter == AIR_SAMPLER_BICUBIC || a->min_filter == AIR_SAMPLER_BICUBIC) {
      say(why, why_size, "the shader's own sampler at index %u asks for filter::bicubic, "
                         "which neither MTLSamplerDescriptor nor this GPU has", index);
      return false;
   }
''',
      '''   if (a->mag_filter == AIR_SAMPLER_BICUBIC || a->min_filter == AIR_SAMPLER_BICUBIC) {
      static bool told;
      if (!told) {
         told = true;
         fprintf(stderr, "SweetNativeMetal: the shader's own sampler at index %u asks for "
                 "filter::bicubic; sampled as linear (no bicubic on this GPU)\\n", index);
      }
   }
'''),
     ('      [AIR_SAMPLER_LINEAR] = RWA_FILTER_LINEAR,\n   };\n',
      '      [AIR_SAMPLER_LINEAR] = RWA_FILTER_LINEAR,\n'
      '      [AIR_SAMPLER_BICUBIC] = RWA_FILTER_LINEAR,   /* approximation, see above */\n   };\n'),
     # Per-draw opaque view (A71 2026-11-23): CoreAnimation's _Ixrg image shaders mean "ignore
     # this layer's alpha". The frontend marks the texture of such a draw; only that draw
     # samples it through a view with alpha = 1. A persistent swizzle on the texture fixed the
     # wallpaper brightness but every other pass that reads Mercury's surface lost its alpha
     # too (the lock-screen clock vanished).
     ('   unsigned char mtl_swizzle[4];    /* MTLTextureSwizzle r, g, b, a; all 0 = none set */\n',
      '   unsigned char mtl_swizzle[4];    /* MTLTextureSwizzle r, g, b, a; all 0 = none set */\n'
      '   struct pipe_sampler_view *view_opaque;   /* alpha = 1, for a draw marked opaque */\n'),
     ('int rwa_texture_set_swizzle(struct rwa_texture *texture, const unsigned char swizzle[4]);\n',
      '/* The texture the next draw on this thread samples as opaque (alpha 1), or NULL. */\n'
      'static _Thread_local struct rwa_texture *rwa_opaque_texture;\n'
      'void rwa_texture_mark_opaque(struct rwa_texture *texture);\n'
      'void\n'
      'rwa_texture_mark_opaque(struct rwa_texture *texture)\n'
      '{\n'
      '   rwa_opaque_texture = texture;\n'
      '}\n\n'
      'int rwa_texture_set_swizzle(struct rwa_texture *texture, const unsigned char swizzle[4]);\n'),
     # Straight-alpha variant of a pipeline's blend state for one draw (A71 2026-11-23,
     # wallpaper depth effect): Mercury's live surface is non-premultiplied rgb with an
     # occlusion mask in alpha (background 0, discs 1). backboardd draws it opaque, then the
     # clock, then again with premultiplied source-over (ONE, 1-a), which added the
     # background rgb a second time (overbright). For that pass the frontend asks for
     # rgb*a + dst*(1-a): the discs cover the clock and nothing is added twice.
     ('   void *blend, *dsa, *rast, *velem;\n',
      '   void *blend, *dsa, *rast, *velem;\n'
      '   struct pipe_blend_state blend_tmpl;   /* what blend was made from */\n'
      '   void *blend_straight;                 /* rgb source factor SRC_ALPHA, made on demand */\n'),
     ('   render->blend = device->pipe->create_blend_state(device->pipe, &blend);\n',
      '   render->blend = device->pipe->create_blend_state(device->pipe, &blend);\n'
      '   render->blend_tmpl = blend;\n'),
     ('   if (render->blend) {\n      pipe->bind_blend_state(pipe, NULL);\n      pipe->delete_blend_state(pipe, render->blend);\n',
      '   if (render->blend_straight) {\n'
      '      pipe->bind_blend_state(pipe, NULL);\n'
      '      pipe->delete_blend_state(pipe, render->blend_straight);\n'
      '   }\n'
      '   if (render->blend) {\n      pipe->bind_blend_state(pipe, NULL);\n      pipe->delete_blend_state(pipe, render->blend);\n'),
     ('   pipe->bind_blend_state(pipe, render->blend);\n',
      '''   void *blend_cso = render->blend;
   if (rwa_straight_alpha_next) {
      if (!render->blend_straight) {
         struct pipe_blend_state s = render->blend_tmpl;
         bool changed = false;
         for (unsigned i = 0; i < PIPE_MAX_COLOR_BUFS; i++) {
            if (s.rt[i].blend_enable && s.rt[i].rgb_src_factor == PIPE_BLENDFACTOR_ONE) {
               s.rt[i].rgb_src_factor = PIPE_BLENDFACTOR_SRC_ALPHA;
               changed = true;
            }
         }
         if (changed)
            render->blend_straight = pipe->create_blend_state(pipe, &s);
      }
      if (render->blend_straight)
         blend_cso = render->blend_straight;
   }
   pipe->bind_blend_state(pipe, blend_cso);
'''),
     ('int rwa_texture_set_swizzle(struct rwa_texture *texture, const unsigned char swizzle[4]);\n',
      '/* The next draw on this thread blends its colour as straight (non-premultiplied) alpha. */\n'
      'static _Thread_local bool rwa_straight_alpha_next;\n'
      'void rwa_render_straight_alpha_next(bool on);\n'
      'void\n'
      'rwa_render_straight_alpha_next(bool on)\n'
      '{\n'
      '   rwa_straight_alpha_next = on;\n'
      '}\n\n'
      'int rwa_texture_set_swizzle(struct rwa_texture *texture, const unsigned char swizzle[4]);\n'),
     ('            struct pipe_sampler_view *use = t->view;\n',
      '            struct pipe_sampler_view *use = t->view;\n'
      '            if (t == rwa_opaque_texture) {\n'
      '               if (!t->view_opaque) {\n'
      '                  struct pipe_sampler_view tmpl = *t->view;\n'
      '                  tmpl.swizzle_a = PIPE_SWIZZLE_1;\n'
      '                  t->view_opaque = pipe->create_sampler_view(pipe, t->res, &tmpl);\n'
      '               }\n'
      '               if (t->view_opaque)\n'
      '                  use = t->view_opaque;\n'
      '            }\n'))

# newBufferWithBytesNoCopy: Mercury's KTX loader makes its staging buffer this way and the
# driver answered nil ("Failed to create staging buffer"). The GPU cannot map the caller's
# pages here, so the bytes are copied into a buffer of our own, and the caller's
# deallocator runs when that buffer goes away, as Metal promises. A caller that writes the
# pages after this call is not seen; the loader fills them first.
edit('tools/mesa/air/air_run.c',
     ('''   unsigned num_img_written = 0;
   for (unsigned i = 0; i < num_img; i++)''',
      '''   if (info->uses_texture_presence) {
      static const uint32_t present = UINT32_MAX; /* The harness supplies every declared texture. */
      pipe->set_constant_buffer(pipe, PIPE_SHADER_COMPUTE, AIR_TEXTURE_PRESENCE_UBO, false,
                                &(struct pipe_constant_buffer){ .user_buffer = &present, .buffer_size = sizeof(present) });
   }
   unsigned num_img_written = 0;
   for (unsigned i = 0; i < num_img; i++)'''),
     ('''   /* every constant buffer the shader reads, filled with the pattern */
   for (unsigned i = 0; i < info.num_resources; i++) {''',
      '''   if (info.uses_texture_presence) {
      static const uint32_t present = UINT32_MAX;
      pipe->set_constant_buffer(pipe, PIPE_SHADER_FRAGMENT, AIR_TEXTURE_PRESENCE_UBO, false,
                                &(struct pipe_constant_buffer){ .user_buffer = &present, .buffer_size = sizeof(present) });
   }
   /* every constant buffer the shader reads, filled with the pattern */
   for (unsigned i = 0; i < info.num_resources; i++) {'''))

edit('userland/src/redwoodmetal.m',
     ('	NSUInteger _nativeParentLevel;\n	int _responsibleProcess;',
      '	NSUInteger _nativeParentLevel;\n	bool _nativeQuartzCoreWallpaperUpload;\n'
      '	int _responsibleProcess;'),
     ('- (id)parentTexture                { NATIVE_OBJECT_LOCK;  return _nativeParentTexture; }\n',
      '- (id)parentTexture                { NATIVE_OBJECT_LOCK;  return _nativeParentTexture; }\n'
      '- (BOOL)nativeQuartzCoreWallpaperUpload { return _nativeQuartzCoreWallpaperUpload; }\n'),
     ('	struct rwa_compute_info _info;\n',
      '	struct rwa_compute_info _info;\n	NSString *_nativeFunctionName;\n'),
     ('- (struct rwa_compute *)compute;\n',
      '- (struct rwa_compute *)compute;\n- (NSString *)nativeFunctionName;\n'),
     ('	_compute = compute;\n	_info = *info;\n',
      '	_compute = compute;\n	_info = *info;\n'
      '	_nativeFunctionName = [[[descriptor computeFunction] name] copy];\n'),
     ('	if (_compute != NULL) {\n		mesa.compute_destroy(_compute);\n	}\n',
      '	if (_compute != NULL) {\n		mesa.compute_destroy(_compute);\n	}\n'
      '	[_nativeFunctionName release];\n'),
     ('- (struct rwa_compute *)compute\n{',
      '- (NSString *)nativeFunctionName { return _nativeFunctionName; }\n\n'
      '- (struct rwa_compute *)compute\n{'),
     ('''	return [[SweetNativeMetalTexture alloc] initWithRedwoodDevice:self
							 texture:texture
							   shape:&shape];
''',
      '''	id result = [[SweetNativeMetalTexture alloc] initWithRedwoodDevice:self
	                                                          texture:texture shape:&shape];
	native_wall_texture_event("allocate", result, __builtin_return_address(0));
	return result;
'''),
     ('''	(void)image;
	if (mesa.texture_write(_texture,''',
      '''	(void)image;
	_nativeQuartzCoreWallpaperUpload |= native_wall_texture_event("upload", self, __builtin_return_address(0));
	if (mesa.texture_write(_texture,'''),
     # DISPATCH trace (processes in /var/local/sweet-mtl-trace, own budget of 160 lines): the
     # grid, the first two textures and the first 8 bytes of buffer 0. Mercury's VariableBlurrer
     # pyramid had levels 2-8 left unwritten (identical means at every level, 2026-11-23);
     # buffer 0 of its downsample holds the source LOD and the target level.
     ('\twork->threadgroupBytes = (unsigned)_threadgroupLength;\n\t[_commandBuffer recordWork:work];\n\t[work release];\n}\n',
      '''\twork->threadgroupBytes = (unsigned)_threadgroupLength;
\tif (sweet_trace_enabled()) {
\t\tstatic int dleft = 160;
\t\tif (__atomic_sub_fetch(&dleft, 1, __ATOMIC_RELAXED) >= 0) {
\t\t\tchar tx[2][96] = { "-", "-" };
\t\t\tfor (unsigned i = 0; i < 2 && i < _highestTexture; i++) {
\t\t\t\tid t = _textures[i];
\t\t\t\tif (t != nil)
\t\t\t\t\tsnprintf(tx[i], sizeof tx[i], "%lux%lu fmt %lu levels %lu usage %#lx",
\t\t\t\t\t         (unsigned long)[t width], (unsigned long)[t height],
\t\t\t\t\t         (unsigned long)[t pixelFormat], (unsigned long)[t mipmapLevelCount],
\t\t\t\t\t         (unsigned long)[t usage]);
\t\t\t}
\t\t\tint16_t b0[4] = { 0 };
\t\t\tif (_highest > 0 && _buffers[0] != nil && [_buffers[0] length] >= (NSUInteger)_offsets[0] + 8) {
\t\t\t\tconst uint8_t *c = (const uint8_t *)[_buffers[0] contents];
\t\t\t\tif (c != NULL)
\t\t\t\t\tmemcpy(b0, c + _offsets[0], sizeof b0);
\t\t\t}
\t\t\tNSString *name = [_pipeline nativeFunctionName];
\t\t\tconst char *pl = name != nil ? [name UTF8String] : "?";
\t\t\tfprintf(stderr, "SweetNativeMetal[%s %d] DISPATCH %s groups %ux%ux%u of %ux%ux%u tex0 %s tex1 %s "
\t\t\t        "b0 %d %d %d %d same %d\\n", getprogname(), getpid(), pl, work->groups[0], work->groups[1],
\t\t\t        work->groups[2], work->size[0], work->size[1], work->size[2], tx[0], tx[1],
\t\t\t        b0[0], b0[1], b0[2], b0[3], _highestTexture > 1 && _textures[0] == _textures[1]);
\t\t}
\t}
\t[_commandBuffer recordWork:work];
\t[work release];
}
'''),
     # MTLTextureSwizzleChannels on views and on IOSurface descriptors (air_metal.c keeps it
     # with the texture). A view that would be the same object is copied by re-import only
     # for IOSurfaces; for others the swizzle is logged and dropped as before.
     ('{ NATIVE_OBJECT_LOCK; \n\t(void)swizzle;\n\treturn [self newTextureViewWithPixelFormat:format textureType:type levels:levels\n\t\t\t\t\t    slices:slices];\n}\n',
      '''{ NATIVE_OBJECT_LOCK;
\tint rwa_texture_set_swizzle(struct rwa_texture *, const unsigned char [4]);
\tid v = [self newTextureViewWithPixelFormat:format textureType:type levels:levels slices:slices];
\tconst unsigned char sw[4] = { (unsigned char)swizzle.red, (unsigned char)swizzle.green,
\t                             (unsigned char)swizzle.blue, (unsigned char)swizzle.alpha };
\tconst bool identity = sw[0] == 2 && sw[1] == 3 && sw[2] == 4 && sw[3] == 5;
\tstatic unsigned told;
\tif (!identity && told++ < 16)
\t\trw_print("texture view swizzle %u%u%u%u format %lu of shape format %u surface %p -> %s\\n",
\t\t         sw[0], sw[1], sw[2], sw[3], (unsigned long)format, _shape.pixel_format, _nativeSurface,
\t\t         v == nil ? "nil" : v == self ? "same object, dropped" : "applied");
\tif (!identity && v != nil && v != self)
\t\trwa_texture_set_swizzle([v mesaTexture], sw);
\treturn v;
}
'''),
     ('    [result nativeAttachSurface:s];return result;\n}\n',
      '''    [result nativeAttachSurface:s];
\tint rwa_texture_set_swizzle(struct rwa_texture *, const unsigned char [4]);
\tif ([d respondsToSelector:@selector(swizzle)]) {
\t\tMTLTextureSwizzleChannels c = [d swizzle];
\t\tconst unsigned char sw[4] = { (unsigned char)c.red, (unsigned char)c.green,
\t\t                             (unsigned char)c.blue, (unsigned char)c.alpha };
\t\tif (!(sw[0] == 2 && sw[1] == 3 && sw[2] == 4 && sw[3] == 5)) {
\t\t\tstatic unsigned told;
\t\t\tif (told++ < 16)
\t\t\t\trw_print("IOSurface texture swizzle %u%u%u%u format %u %ux%u\\n", sw[0], sw[1], sw[2],
\t\t\t\t         sw[3], shape.pixel_format, shape.width, shape.height);
\t\t\trwa_texture_set_swizzle(texture, sw);
\t\t}
\t}
\treturn result;
}
'''),
     ('@implementation SweetNativeMetalDevice\n',
      '''@interface SweetNativeNoCopyRelease : NSObject {
	void (^_deallocator)(void *, NSUInteger);
	void *_bytes;
	NSUInteger _length;
}
- (instancetype)initWithDeallocator:(void (^)(void *, NSUInteger))d bytes:(void *)b length:(NSUInteger)n;
@end

@implementation SweetNativeNoCopyRelease
- (instancetype)initWithDeallocator:(void (^)(void *, NSUInteger))d bytes:(void *)b length:(NSUInteger)n
{
	self = [super init];
	if (self != nil) {
		_deallocator = d ? [d copy] : nil;
		_bytes = b;
		_length = n;
	}
	return self;
}
- (void)dealloc
{
	if (_deallocator != nil) {
		_deallocator(_bytes, _length);
		[_deallocator release];
	}
	[super dealloc];
}
@end

static char sweet_nocopy_key;

@implementation SweetNativeMetalDevice
'''),
     ('''	(void)bytes; (void)length; (void)options; (void)deallocator;
	return nil;   /* wrapping the caller's own pages needs the kernel to map them: not yet */''',
      '''	if (bytes == NULL || length == 0)
		return nil;
	id buffer = [self newBufferWithLength:length options:options];
	if (buffer == nil || [buffer contents] == NULL) {
		[buffer release];
		return nil;
	}
	memcpy([buffer contents], bytes, length);
	RW_ONCE("newBufferWithBytesNoCopy: %lu bytes copied (the caller's pages are not "
		"mapped into the GPU; later writes to them are not seen)\\n", (unsigned long)length);
	if (deallocator != nil) {
		SweetNativeNoCopyRelease *r = [[SweetNativeNoCopyRelease alloc]
			initWithDeallocator:deallocator bytes:bytes length:length];
		objc_setAssociatedObject(buffer, &sweet_nocopy_key, r, OBJC_ASSOCIATION_RETAIN);
		[r release];
	}
	return buffer;'''),
     # A blit encoder. There was none (-blitCommandEncoder answered nil), and Mercury
     # uploads its wallpaper textures through one ("Failed to create blit encoder for
     # private texture upload"). Every copy here runs when it is encoded, through the same
     # texel path as -replaceRegion:; a blit that depends on GPU work encoded earlier in the
     # same command buffer would see it undone, which an upload before a commit does not.
     ('@implementation SweetNativeMetalCommandBuffer {\n',
      '''int rwa_texture_generate_mipmap(struct rwa_texture *texture);
int rwa_texture_resolve(struct rwa_texture *src, struct rwa_texture *dst, unsigned level,
                        unsigned slice, bool external, unsigned trace_seq);

@interface SweetNativeMetalBlitEncoder : NSObject {
	id _device;
	SweetNativeMetalCommandBuffer *_cb;   /* not retained: it owns the encoder's life */
	NSString *_label;
}
- (instancetype)initWithCommandBuffer:(SweetNativeMetalCommandBuffer *)cb device:(id)device;
@end

/* Every blit is queued on the command buffer as work and runs in order with the passes
 * around it at commit: CoreAnimation draws a texture, asks for its mipmaps and samples
 * them, all in one command buffer, so a blit run at encode time would see the texture
 * before the draw. */
@implementation SweetNativeMetalBlitEncoder
+ (void)load
{
	Protocol *p = objc_getProtocol("MTLBlitCommandEncoder");
	if (p != NULL && !class_conformsToProtocol(self, p))
		class_addProtocol(self, p);
}
- (instancetype)initWithCommandBuffer:(SweetNativeMetalCommandBuffer *)cb device:(id)device
{
	self = [super init];
	if (self != nil) {
		_cb = cb;
		_device = [device retain];
	}
	return self;
}
- (void)dealloc { [_device release]; [_label release]; [super dealloc]; }
- (void)enqueue:(void (^)(void))op
{
	SweetNativeMetalWork *work = [SweetNativeMetalWork new];
	work->nativeBlit = [op copy];
	[_cb recordWork:work];
	[work release];
}
- (id)device { return _device; }
- (NSString *)label { return _label; }
- (void)setLabel:(NSString *)l { [_label release]; _label = [l copy]; }
- (void)endEncoding {}
- (void)insertDebugSignpost:(NSString *)s { (void)s; }
- (void)pushDebugGroup:(NSString *)s { (void)s; }
- (void)popDebugGroup {}
- (void)updateFence:(id)f { (void)f; }
- (void)waitForFence:(id)f { (void)f; }
- (void)synchronizeResource:(id)r { (void)r; }
- (void)synchronizeTexture:(id)t slice:(NSUInteger)s level:(NSUInteger)l { (void)t; (void)s; (void)l; }
- (void)optimizeContentsForGPUAccess:(id)t { (void)t; }
- (void)optimizeContentsForCPUAccess:(id)t { (void)t; }
- (void)copyFromBuffer:(id)src sourceOffset:(NSUInteger)off sourceBytesPerRow:(NSUInteger)bpr
   sourceBytesPerImage:(NSUInteger)bpi sourceSize:(MTLSize)size toTexture:(id)dst
      destinationSlice:(NSUInteger)slice destinationLevel:(NSUInteger)level
     destinationOrigin:(MTLOrigin)origin options:(NSUInteger)options
{
	(void)options;
	if (src == nil || dst == nil)
		return;
	[self enqueue:^{
		const uint8_t *bytes = (const uint8_t *)[src contents];
		if (bytes != NULL)
			[dst replaceRegion:MTLRegionMake3D(origin.x, origin.y, origin.z, size.width, size.height, size.depth)
			       mipmapLevel:level slice:slice withBytes:bytes + off bytesPerRow:bpr bytesPerImage:bpi];
	}];
}
- (void)copyFromBuffer:(id)src sourceOffset:(NSUInteger)off sourceBytesPerRow:(NSUInteger)bpr
   sourceBytesPerImage:(NSUInteger)bpi sourceSize:(MTLSize)size toTexture:(id)dst
      destinationSlice:(NSUInteger)slice destinationLevel:(NSUInteger)level
     destinationOrigin:(MTLOrigin)origin
{
	[self copyFromBuffer:src sourceOffset:off sourceBytesPerRow:bpr sourceBytesPerImage:bpi
		  sourceSize:size toTexture:dst destinationSlice:slice destinationLevel:level
	   destinationOrigin:origin options:0];
}
- (void)copyFromTexture:(id)src sourceSlice:(NSUInteger)ss sourceLevel:(NSUInteger)sl
           sourceOrigin:(MTLOrigin)so sourceSize:(MTLSize)size toBuffer:(id)dst
      destinationOffset:(NSUInteger)off destinationBytesPerRow:(NSUInteger)bpr
    destinationBytesPerImage:(NSUInteger)bpi options:(NSUInteger)options
{
	(void)options;
	if (src == nil || dst == nil)
		return;
	[self enqueue:^{
		uint8_t *bytes = (uint8_t *)[dst contents];
		if (bytes != NULL)
			[src getBytes:bytes + off bytesPerRow:bpr bytesPerImage:bpi
			   fromRegion:MTLRegionMake3D(so.x, so.y, so.z, size.width, size.height, size.depth)
			  mipmapLevel:sl slice:ss];
	}];
}
- (void)copyFromTexture:(id)src sourceSlice:(NSUInteger)ss sourceLevel:(NSUInteger)sl
           sourceOrigin:(MTLOrigin)so sourceSize:(MTLSize)size toBuffer:(id)dst
      destinationOffset:(NSUInteger)off destinationBytesPerRow:(NSUInteger)bpr
    destinationBytesPerImage:(NSUInteger)bpi
{
	[self copyFromTexture:src sourceSlice:ss sourceLevel:sl sourceOrigin:so sourceSize:size
		     toBuffer:dst destinationOffset:off destinationBytesPerRow:bpr
	     destinationBytesPerImage:bpi options:0];
}
/* texture to texture through memory of our own: 16 bytes a texel is the widest format
 * there is, so the row is long enough for any of them, block formats included */
- (void)copyFromTexture:(id)src sourceSlice:(NSUInteger)ss sourceLevel:(NSUInteger)sl
           sourceOrigin:(MTLOrigin)so sourceSize:(MTLSize)size toTexture:(id)dst
       destinationSlice:(NSUInteger)ds destinationLevel:(NSUInteger)dl
      destinationOrigin:(MTLOrigin)dorg
{
	if (src == nil || dst == nil || size.width == 0 || size.height == 0)
		return;
	[self enqueue:^{
		NSUInteger depth = size.depth ? size.depth : 1;
		NSUInteger bpr = size.width * 16, bpi = bpr * size.height;
		uint8_t *tmp = malloc(bpi * depth);
		if (tmp == NULL)
			return;
		[src getBytes:tmp bytesPerRow:bpr bytesPerImage:bpi
		   fromRegion:MTLRegionMake3D(so.x, so.y, so.z, size.width, size.height, depth)
		  mipmapLevel:sl slice:ss];
		[dst replaceRegion:MTLRegionMake3D(dorg.x, dorg.y, dorg.z, size.width, size.height, depth)
		       mipmapLevel:dl slice:ds withBytes:tmp bytesPerRow:bpr bytesPerImage:bpi];
		free(tmp);
	}];
}
- (void)copyFromTexture:(id)src toTexture:(id)dst
{
	NSUInteger levels = MIN([src mipmapLevelCount], [dst mipmapLevelCount]);
	for (NSUInteger l = 0; l < levels; l++) {
		NSUInteger w = MAX([src width] >> l, 1), h = MAX([src height] >> l, 1);
		[self copyFromTexture:src sourceSlice:0 sourceLevel:l sourceOrigin:MTLOriginMake(0, 0, 0)
			   sourceSize:MTLSizeMake(w, h, 1) toTexture:dst destinationSlice:0
		     destinationLevel:l destinationOrigin:MTLOriginMake(0, 0, 0)];
	}
}
/* whole levels and slices (iOS 26 form; Mercury uses it) */
- (void)copyFromTexture:(id)src sourceSlice:(NSUInteger)ss sourceLevel:(NSUInteger)sl
              toTexture:(id)dst destinationSlice:(NSUInteger)ds destinationLevel:(NSUInteger)dl
             sliceCount:(NSUInteger)sc levelCount:(NSUInteger)lc
{
	if (src == nil || dst == nil)
		return;
	for (NSUInteger l = 0; l < lc; l++) {
		NSUInteger w = MAX([src width] >> (sl + l), 1), h = MAX([src height] >> (sl + l), 1);
		for (NSUInteger s = 0; s < sc; s++)
			[self copyFromTexture:src sourceSlice:ss + s sourceLevel:sl + l
				 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(w, h, 1)
				    toTexture:dst destinationSlice:ds + s destinationLevel:dl + l
			    destinationOrigin:MTLOriginMake(0, 0, 0)];
	}
}
- (void)copyFromBuffer:(id)src sourceOffset:(NSUInteger)so toBuffer:(id)dst
     destinationOffset:(NSUInteger)doff size:(NSUInteger)n
{
	if (src == nil || dst == nil || n == 0)
		return;
	[self enqueue:^{
		uint8_t *s = (uint8_t *)[src contents], *d = (uint8_t *)[dst contents];
		if (s != NULL && d != NULL)
			memmove(d + doff, s + so, n);
	}];
}
- (void)fillBuffer:(id)b range:(NSRange)r value:(uint8_t)v
{
	if (b == nil || r.length == 0)
		return;
	[self enqueue:^{
		uint8_t *d = (uint8_t *)[b contents];
		if (d != NULL)
			memset(d + r.location, v, r.length);
	}];
}
/* the levels below the base, made by the GPU from the base (Gallium's util_gen_mipmap) */
- (void)generateMipmapsForTexture:(id)t
{
	if (t == nil || ![t respondsToSelector:@selector(mesaTexture)])
		return;
	[self enqueue:^{
		if (rwa_texture_generate_mipmap([t mesaTexture]) != 0)
			RW_ONCE("blit: generateMipmapsForTexture: failed\\n");
	}];
}
/* anything else a blit encoder is asked does nothing rather than abort the caller */
- (NSMethodSignature *)methodSignatureForSelector:(SEL)s
{
	NSMethodSignature *m = [super methodSignatureForSelector:s];
	return m ? m : [NSMethodSignature signatureWithObjCTypes:"v@:"];
}
- (void)forwardInvocation:(NSInvocation *)inv
{
	RW_ONCE("blit: %s is not implemented and was skipped\\n", sel_getName([inv selector]));
}
@end

@implementation SweetNativeMetalCommandBuffer {
'''),
     ('- (id)blitCommandEncoder          { NATIVE_OBJECT_LOCK;  return nil; }',
      '''- (id)blitCommandEncoder
{ NATIVE_OBJECT_LOCK;
	return [[[SweetNativeMetalBlitEncoder alloc] initWithCommandBuffer:self device:[_queue device]] autorelease];
}
- (id)blitCommandEncoderWithDescriptor:(id)d { (void)d; return [self blitCommandEncoder]; }'''),
     ('\tBOOL hasDepthRange;\n', '\tBOOL hasDepthRange;\n\tid nativeBlit;   /* a queued blit: a block run in order at commit */\n'),
     ('    for(unsigned i=0;i<8;i++)[color[i] release];\n',
      '    for(unsigned i=0;i<8;i++)[color[i] release];\n    [nativeBlit release];\n'),
     ('        if(work->nativeBarrier) {\n',
      '        if(work->nativeBlit) {\n            ((void (^)(void))work->nativeBlit)();\n            continue;\n        }\n        if(work->nativeBarrier) {\n'),
     # dispatchThreads with a grid that does not divide into the threadgroup size (Metal's
     # non-uniform threadgroups). Mercury's VariableBlurrer and VideoToolbox dispatch 207x448 in
     # 32x32 groups and every one was refused, so the wallpaper never rendered. freedreno has
     # no partial last group (pipe_grid_info.last_block is ignored), so the groups are rounded
     # up: the extra threads at the far edge read textures clamped, and the Adreno drops image
     # and IBO stores outside the descriptor's size.
     ('''	if (size.width == 0 || size.height == 0 || size.depth == 0 ||
	    threads.width % size.width != 0 || threads.height % size.height != 0 ||
	    threads.depth % size.depth != 0) {
		rw_print("%lux%lux%lu threads do not divide into groups of "''',
      '''	if (size.width != 0 && size.height != 0 && size.depth != 0 &&
	    (threads.width % size.width != 0 || threads.height % size.height != 0 ||
	     threads.depth % size.depth != 0)) {
		RW_ONCE("dispatchThreads: %lux%lux%lu threads in groups of %lux%lux%lu rounded up to whole "
		        "groups (no partial groups on this GPU)\\n", (unsigned long)threads.width,
		        (unsigned long)threads.height, (unsigned long)threads.depth,
		        (unsigned long)size.width, (unsigned long)size.height, (unsigned long)size.depth);
		groups.width = (threads.width + size.width - 1) / size.width;
		groups.height = (threads.height + size.height - 1) / size.height;
		groups.depth = (threads.depth + size.depth - 1) / size.depth;
		[self dispatchThreadgroups:groups threadsPerThreadgroup:size];
		return;
	}
	if (size.width == 0 || size.height == 0 || size.depth == 0) {
		rw_print("%lux%lux%lu threads do not divide into groups of "'''),
     # Multisample resolve: recorded per colour attachment, queued at -endEncoding as a GPU
     # blit run in order after the pass's draws (rwa_texture_resolve).
     ('\tunsigned _fragmentTextureCount, _fragmentSamplerCount;\n\tBOOL _complained;\n}',
      '\tunsigned _fragmentTextureCount, _fragmentSamplerCount;\n\tBOOL _complained;\n'
      '\tid _resolve[8];\n\tNSUInteger _resolveLevel[8], _resolveSlice[8];\n}'),
     ('''\t\tif (store == MTLStoreActionMultisampleResolve ||
\t\t    store == MTLStoreActionStoreAndMultisampleResolve ||
\t\t    [attachment resolveTexture] != nil) {''',
      '''\t\tif ([attachment resolveTexture] != nil &&
\t\t    [[attachment resolveTexture] respondsToSelector:@selector(mesaTexture)] &&
\t\t    [texture respondsToSelector:@selector(mesaTexture)] &&
\t\t    (store == MTLStoreActionMultisampleResolve ||
\t\t     store == MTLStoreActionStoreAndMultisampleResolve)) {
\t\t\t_resolve[i] = [[attachment resolveTexture] retain];
\t\t\t_resolveLevel[i] = [attachment resolveLevel];
\t\t\t_resolveSlice[i] = [attachment resolveSlice];
\t\t} else if (store == MTLStoreActionMultisampleResolve ||
\t\t    store == MTLStoreActionStoreAndMultisampleResolve ||
\t\t    [attachment resolveTexture] != nil) {'''),
     ('''    [super endEncoding];
}

@end

@implementation SweetNativeMetalComputeEncoder''',
      '''    for (unsigned i = 0; i < 8; i++) {
        if (_resolve[i] == nil)
            continue;
        id src = _color[i], dst = _resolve[i];
        unsigned lvl = (unsigned)_resolveLevel[i], sl = (unsigned)_resolveSlice[i];
        if (src != nil) {
            SweetNativeMetalWork *work = [SweetNativeMetalWork new];
            work->nativeBlit = [^{
                void *surface = [dst respondsToSelector:@selector(iosurface)] ? (void *)[dst iosurface] : NULL;
                bool stage_external = surface != NULL && !strcmp(getprogname(), "MercuryPosterExtension");
                unsigned seq = 0;
                if (sweet_trace_enabled() && lvl == 0 && sl == 0 &&
                    [src sampleCount] > 1 && [dst sampleCount] == 1) {
                    static unsigned logged[2];
                    unsigned index = surface != NULL;
                    if (logged[index] < 2)
                        seq = ++logged[index] + (index ? 9002 : 9000);
                }
                if (rwa_texture_resolve([src mesaTexture], [dst mesaTexture], lvl, sl, stage_external, seq) != 0)
                    RW_ONCE("a multisample resolve failed\\n");
                else {
                    sweet_trace("resolve %p -> %p level %u slice %u blitted", src, dst, lvl, sl);
                    /* Read the single-sample result, since getBytes rejects the MSAA attachment. */
                    if (seq) {
                        rw_print("TEXSTAT %u resolved color %p surface %p\\n", seq, dst, surface);
                        native_drawlog_texstat(seq, dst);
                    }
                }
            } copy];
            [_commandBuffer recordWork:work];
            [work release];
        }
        [_resolve[i] release];
        _resolve[i] = nil;
    }
    [super endEncoding];
}

@end

@implementation SweetNativeMetalComputeEncoder'''),
     # The glass samples blur textures whose mipmapLevelCount reads 0 (draw trace
     # 2026-11-20 night): say who asks for such a texture, the first 16 times.
     ('''		.mip_levels = (unsigned)[descriptor mipmapLevelCount],
		.sample_count = (unsigned)[descriptor sampleCount],
		.usage = (unsigned)[descriptor usage],
	};
''',
      '''		.mip_levels = (unsigned)[descriptor mipmapLevelCount],
		.sample_count = (unsigned)[descriptor sampleCount],
		.usage = (unsigned)[descriptor usage],
	};
	if (shape.mip_levels == 0) {
		static unsigned told0;
		if (told0++ < 16)
			rw_print("texture with mipmapLevelCount 0: format %u type %u %ux%u usage %#x "
			         "storage %lu descriptor %s\\n", shape.pixel_format, shape.type, shape.width,
			         shape.height, shape.usage, (unsigned long)[descriptor storageMode],
			         class_getName(object_getClass(descriptor)));
	}
'''),
     # GLASSSTAT: every draw is counted by kind (SweetNativeDrawLog.inc)
     ('\tconst unsigned dl = native_drawlog_next();\n',
      '\tnative_glassstat([work->render render]);\n'
      '\tif (native_skip_luma_boost([work->render render]))\n\t\treturn YES;\n'
      '\tnative_xrg_alpha_one([work->render render], work->textures, work->textureCount);\n'
      '\tnative_mercury_occl_trace([work->render render], work->color, work->colorCount,\n'
      '\t                          work->buffers, work->bufferOffsets, work->count);\n'
      '\tnative_glass_uniform_trace([work->render render], work->color, work->colorCount,\n'
      '\t                           work->buffers, work->bufferOffsets, work->count, work->textures, work->textureCount);\n'
      '\tnative_vblur_trace([work->render render], work->color, work->colorCount, work->buffers,\n'
      '\t                   work->bufferOffsets, work->count, work->textures, work->textureCount,\n'
      '\t                   work->vertexBuffers, work->vertexBufferOffsets, work->vertexBufferCount,\n'
      '\t                   work->vertexStart, work->vertexCount, work->indexBuffer != nil);\n'
      '\tnative_vblur_mask_copy([work->render render], work->textures, work->textureCount);\n'
      '\tnative_vblur_capture([work->render render], work->color, work->colorCount, work->buffers,\n'
      '\t                     work->bufferOffsets, work->count, work->textures, work->textureCount,\n'
      '\t                     work->vertexBuffers, work->vertexBufferOffsets, work->vertexBufferCount,\n'
      '\t                     work->primitive, work->vertexStart, work->vertexCount, work->baseVertex,\n'
      '\t                     work->indexBuffer, work->indexType, work->indexBufferOffset);\n'
      '\tif (native_wall_skip_repeated_surface(self, [work->render render], work->color,\n'
      '\t                                      work->colorCount, work->textures, work->textureCount,\n'
      '\t                                      work->depth != nil, work->vertexCount,\n'
      '\t                                      work->nativeFlags, work->nativeViewport, work->nativeScissor))\n'
      '\t\treturn YES;\n'
      '\tif (native_wall_skip_uploaded_overlay(self, [work->render render], work->color,\n'
      '\t                                      work->colorCount, work->textures, work->textureCount))\n'
      '\t\treturn YES;\n'
      '\tconst unsigned dl = native_drawlog_next();\n'),
     # MTLHeap: Mercury's look preview allocates its textures from a heap. The device answered
     # nil (and a zero size-and-align), Mercury logged "unable to create heap: 0", and
     # uber_fragment then ran with no texture bound. A heap here is bookkeeping: each resource
     # it hands out is an ordinary allocation of the device's, so aliasing never shares memory
     # (contents of an aliased resource are undefined in Metal anyway).
     ('\tif (mesa.render_draw([work->render render], &draw, why, size) != 0) {\n',
      '\tconst bool probe_glass = native_glass_pixels_should_sample([work->render render]);\n'
      '\tif (probe_glass)\n'
      '\t\tnative_glass_pixels("before", work->color, work->colorCount, work->textures, work->textureCount,\n'
      '\t\t                    work->nativeScissor, work->nativeFlags);\n'
      '\tconst int native_draw_rc = mesa.render_draw([work->render render], &draw, why, size);\n'
      '\tnative_xrg_clear();\n'
      '\tif (probe_glass && native_draw_rc == 0)\n'
      '\t\tnative_glass_pixels("after", work->color, work->colorCount, work->textures, work->textureCount,\n'
      '\t\t                    work->nativeScissor, work->nativeFlags);\n'
      '\tif (native_draw_rc != 0) {\n'),
     ('@implementation SweetNativeMetalDevice\n',
      r'''@interface SweetNativeMetalHeap : NSObject {
	id _device;
	NSString *_label;
	NSUInteger _size, _used, _storageMode, _cpuCacheMode, _hazardTrackingMode, _type, _options;
}
- (instancetype)initWithDevice:(id)device descriptor:(MTLHeapDescriptor *)descriptor;
@end

static NSUInteger sweet_heap_texture_bytes(MTLTextureDescriptor *d)
{
	NSUInteger w = MAX([d width], (NSUInteger)1), h = MAX([d height], (NSUInteger)1);
	NSUInteger z = MAX([d depth], (NSUInteger)1), levels = MAX([d mipmapLevelCount], (NSUInteger)1);
	NSUInteger layers = MAX([d arrayLength], (NSUInteger)1) * MAX([d sampleCount], (NSUInteger)1);
	NSUInteger type = [d textureType], total = 0;

	if (type == 5 || type == 6)   /* Cube, CubeArray */
		layers *= 6;
	for (NSUInteger l = 0; l < levels && l < 16; l++) {
		total += w * h * z;
		w = MAX(w / 2, (NSUInteger)1); h = MAX(h / 2, (NSUInteger)1); z = MAX(z / 2, (NSUInteger)1);
	}
	/* 16 bytes a texel is the widest format: an over-estimate costs nothing, the heap is not
	 * one allocation here. */
	total = total * layers * 16;
	return (total + 0xffff) & ~(NSUInteger)0xffff;
}

@implementation SweetNativeMetalHeap
+ (void)load
{
	Protocol *p = objc_getProtocol("MTLHeap");

	if (p != NULL && !class_conformsToProtocol(self, p) && !class_addProtocol(self, p))
		rw_print("class_addProtocol(MTLHeap) refused\n");
}
- (instancetype)initWithDevice:(id)device descriptor:(MTLHeapDescriptor *)descriptor
{
	self = [super init];
	if (self != nil) {
		_device = [device retain];
		_size = [descriptor size];
		_storageMode = [descriptor storageMode];
		_cpuCacheMode = [descriptor cpuCacheMode];
		_hazardTrackingMode = [descriptor hazardTrackingMode];
		_type = [descriptor type];
		_options = [descriptor resourceOptions];
	}
	return self;
}
- (void)dealloc { [_device release]; [_label release]; [super dealloc]; }
- (id)device                        { return _device; }
- (NSString *)label                 { NATIVE_OBJECT_LOCK; return _label; }
- (void)setLabel:(NSString *)label  { NATIVE_OBJECT_LOCK; [_label release]; _label = [label copy]; }
- (NSUInteger)storageMode           { return _storageMode; }
- (NSUInteger)cpuCacheMode          { return _cpuCacheMode; }
- (NSUInteger)hazardTrackingMode    { return _hazardTrackingMode; }
- (NSUInteger)resourceOptions       { return _options; }
- (NSUInteger)type                  { return _type; }
- (NSUInteger)size                  { return _size; }
- (NSUInteger)usedSize              { NATIVE_OBJECT_LOCK; return MIN(_used, _size); }
- (NSUInteger)currentAllocatedSize  { return _size; }
- (NSUInteger)maxAvailableSizeWithAlignment:(NSUInteger)alignment
{
	(void)alignment;
	return _size;   /* nothing is carved out of it, so all of it stays available */
}
- (NSUInteger)setPurgeableState:(NSUInteger)state { (void)state; return 2; }
- (id)newBufferWithLength:(NSUInteger)length options:(NSUInteger)options
{ NATIVE_OBJECT_LOCK;
	id buffer = [_device newBufferWithLength:length options:options];
	if (buffer != nil)
		_used += length;
	return buffer;
}
- (id)newBufferWithLength:(NSUInteger)length options:(NSUInteger)options offset:(NSUInteger)offset
{
	(void)offset;
	return [self newBufferWithLength:length options:options];
}
- (id)newTextureWithDescriptor:(MTLTextureDescriptor *)descriptor
{ NATIVE_OBJECT_LOCK;
	id texture = [_device newTextureWithDescriptor:descriptor];
	static unsigned told;
	if (told++ < 8)
		rw_print("heap %p (%lu bytes): texture format %lu %lux%lu levels %lu -> %p\n", self,
		         (unsigned long)_size, (unsigned long)[descriptor pixelFormat],
		         (unsigned long)[descriptor width], (unsigned long)[descriptor height],
		         (unsigned long)[descriptor mipmapLevelCount], texture);
	if (texture != nil)
		_used += sweet_heap_texture_bytes(descriptor);
	return texture;
}
- (id)newTextureWithDescriptor:(MTLTextureDescriptor *)descriptor offset:(NSUInteger)offset
{
	(void)offset;
	return [self newTextureWithDescriptor:descriptor];
}
- (id)newAccelerationStructureWithSize:(NSUInteger)size { (void)size; return nil; }
- (id)newAccelerationStructureWithSize:(NSUInteger)size offset:(NSUInteger)offset
{ (void)size; (void)offset; return nil; }
- (id)newAccelerationStructureWithDescriptor:(id)descriptor { (void)descriptor; return nil; }
- (id)newAccelerationStructureWithDescriptor:(id)descriptor offset:(NSUInteger)offset
{ (void)descriptor; (void)offset; return nil; }
/* Anything else a caller sends is logged and answered with zero instead of terminate(), so
 * the next missing selector is a log line and not a dead wallpaper extension. */
- (NSMethodSignature *)methodSignatureForSelector:(SEL)sel
{
	NSMethodSignature *s = [super methodSignatureForSelector:sel];
	return s != nil ? s : [NSMethodSignature signatureWithObjCTypes:"@@:"];
}
- (void)forwardInvocation:(NSInvocation *)invocation
{
	static unsigned told;
	if (told++ < 16)
		rw_print("heap: unanswered selector %s, returning zero\n", sel_getName([invocation selector]));
}
@end

@implementation SweetNativeMetalDevice
'''),
     # supportsFamily: Mercury's wallpaper never encodes a draw although its frame loop runs; it
     # asks -supportsFamily: and profile 0 claims Apple1/Common1 only. Raising metal_profile
     # aborted backboardd on iOS 16, so instead: log every family each process asks about, and
     # let /var/local/sweet-mtl-families ("PROCESS FAMILY [FAMILY...]" lines) answer YES for
     # one process without touching anyone else.
     ("/* Profile 0's own table says maxVertexAmplificationCount is 1, so anything above one is\n",
      r"""static BOOL sweet_family_override(NSInteger family)
{
	static int loaded;
	static NSInteger fams[16];
	static unsigned nfams;
	if (!loaded) {
		loaded = 1;
		FILE *f = fopen("/var/local/sweet-mtl-families", "r");
		if (f != NULL) {
			char line[256];
			while (fgets(line, sizeof(line), f) != NULL) {
				char *save = NULL, *tok = strtok_r(line, " \t\r\n", &save);
				if (tok == NULL || strcmp(tok, getprogname()) != 0)
					continue;
				while ((tok = strtok_r(NULL, " \t\r\n", &save)) != NULL && nfams < 16)
					fams[nfams++] = (NSInteger)strtol(tok, NULL, 10);
			}
			fclose(f);
		}
	}
	for (unsigned i = 0; i < nfams; i++)
		if (fams[i] == family)
			return YES;
	return NO;
}

- (BOOL)supportsFamily:(NSInteger)family
{ NATIVE_OBJECT_LOCK;
	struct objc_super sup = { self, class_getSuperclass([SweetNativeMetalDevice class]) };
	BOOL r = ((BOOL (*)(struct objc_super *, SEL, NSInteger))objc_msgSendSuper)(&sup, _cmd, family);
	BOOL o = !r && sweet_family_override(family);
	static NSInteger told[32];
	static unsigned ntold;
	BOOL seen = NO;
	for (unsigned i = 0; i < ntold; i++)
		seen |= told[i] == family;
	if (!seen && ntold < 32) {
		told[ntold++] = family;
		rw_print("supportsFamily %ld -> %s%s\n", (long)family, (r || o) ? "YES" : "NO",
		         o ? " (sweet-mtl-families override)" : "");
	}
	return r || o;
}

/* Profile 0's own table says maxVertexAmplificationCount is 1, so anything above one is
"""),
     ('- (id)newHeapWithDescriptor:(id)descriptor { NATIVE_OBJECT_LOCK;  (void)descriptor; return nil; }\n',
      r'''- (id)newHeapWithDescriptor:(id)descriptor
{ NATIVE_OBJECT_LOCK;
	NSUInteger size = descriptor != nil ? [(MTLHeapDescriptor *)descriptor size] : 0;
	id heap = size != 0 ? [[SweetNativeMetalHeap alloc] initWithDevice:self descriptor:descriptor] : nil;
	static unsigned told;
	if (told++ < 8)
		rw_print("newHeapWithDescriptor: size %lu -> %p\n", (unsigned long)size, heap);
	return heap;
}
'''),
     ('\t(void)length; (void)options;\n\treturn (MTLSizeAndAlign){ 0, 0 };\n',
      '\t(void)options;\n\treturn (MTLSizeAndAlign){ (length + 255) & ~(NSUInteger)255, 256 };\n'),
     ('\t(void)descriptor;\n\treturn (MTLSizeAndAlign){ 0, 0 };\n',
      '\treturn (MTLSizeAndAlign){ sweet_heap_texture_bytes(descriptor), 0x10000 };\n'),
     # -[MTLCommandQueue commandBufferWithDescriptor:] (Swift makeCommandBuffer(descriptor:)).
     # This queue never had it, so the call went to _MTLCommandQueue's own method, which the
     # "unimplemented" log cannot see. Mercury's Space poster calls it (selector in its binary),
     # takes a drawable every frame and never committed a command buffer for one: guess, not
     # disassembled, that the base method answers nil like _MTLDevice's command-queue stub.
     # The descriptor's retainedReferences / errorOptions / logState change nothing here.
     ('- (id)commandBufferWithUnretainedReferences\n{\n\treturn [self commandBuffer];\n}\n',
      r'''- (id)commandBufferWithUnretainedReferences
{
	return [self commandBuffer];
}

- (id)commandBufferWithDescriptor:(id)descriptor
{
	static unsigned calls;
	unsigned n = __atomic_add_fetch(&calls, 1, __ATOMIC_RELAXED);
	if (n <= 3 || (n & 1023) == 0)
		rw_print("commandBufferWithDescriptor: call %u answered with an ordinary command buffer "
		         "(descriptor %p: retained references and error options are not separate here)\n",
		         n, descriptor);
	return [self commandBuffer];
}
'''),
     # Command-buffer life trace for the processes named in /var/local/sweet-mtl-trace
     # (getprogname() names, whitespace separated), 600 lines per process. Mercury's Space
     # poster takes a drawable every frame and commits nothing after setup, without any
     # refusal in the log: this says where a frame stops (slot wait, encoder, draws, commit).
     ('@interface SweetNativeNoCopyRelease : NSObject {\n',
      r'''static int sweet_trace_enabled(void)
{
	static int on;
	static dispatch_once_t once;
	dispatch_once(&once, ^{
		FILE *f = fopen("/var/local/sweet-mtl-trace", "r");
		char word[128];
		if (f == NULL)
			return;
		while (fscanf(f, "%127s", word) == 1)
			if (strcmp(word, getprogname()) == 0)
				on = 1;
		fclose(f);
		if (on)
			fprintf(stderr, "SweetNativeMetal[%s %d] TRACE on (/var/local/sweet-mtl-trace), 600 lines\n",
			        getprogname(), getpid());
	});
	return on;
}

static void sweet_trace(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void sweet_trace(const char *fmt, ...)
{
	static int left = 600;
	char line[512];
	uint64_t tid = 0;
	va_list ap;

	if (!sweet_trace_enabled() || __atomic_sub_fetch(&left, 1, __ATOMIC_RELAXED) < 0)
		return;
	pthread_threadid_np(NULL, &tid);
	va_start(ap, fmt);
	vsnprintf(line, sizeof line, fmt, ap);
	va_end(ap);
	fprintf(stderr, "SweetNativeMetal[%s %d] TRACE t%llu: %s\n", getprogname(), getpid(),
	        (unsigned long long)tid, line);
}

@interface SweetNativeNoCopyRelease : NSObject {
'''),
     ('- (id)commandBuffer\n{\n\treturn [[[SweetNativeMetalCommandBuffer alloc] initWithRedwoodQueue:self] autorelease];\n}\n',
      r'''- (id)commandBuffer
{
	sweet_trace("queue %p commandBuffer: asking (waits here while every slot is held)", self);
	id cb = [[[SweetNativeMetalCommandBuffer alloc] initWithRedwoodQueue:self] autorelease];
	sweet_trace("queue %p commandBuffer -> %p", self, cb);
	return cb;
}
'''),
     ('- (void)commit\n{ NATIVE_OBJECT_LOCK; \n\tchar why[512] = { 0 };\n',
      '- (void)commit\n{ NATIVE_OBJECT_LOCK; \n\tchar why[512] = { 0 };\n'
      '\tsweet_trace("cb %p commit: %lu works, status %lu", self, (unsigned long)[_work count], (unsigned long)_status);\n'),
     ('- (void)addCompletedHandler:(void (^)(id))handler\n{ NATIVE_OBJECT_LOCK; \n',
      '- (void)addCompletedHandler:(void (^)(id))handler\n{ NATIVE_OBJECT_LOCK; \n'
      '\tsweet_trace("cb %p addCompletedHandler (status %lu)", self, (unsigned long)_status);\n'),
     ('- (void)waitUntilScheduled { NATIVE_OBJECT_LOCK;  }\n',
      '- (void)waitUntilScheduled { NATIVE_OBJECT_LOCK;  sweet_trace("cb %p waitUntilScheduled", self); }\n'),
     ('    atomic_fetch_add(&native_wait_until_completed,1);\n',
      '    atomic_fetch_add(&native_wait_until_completed,1);\n'
      '\tsweet_trace("cb %p waitUntilCompleted (status %lu)", self, (unsigned long)_status);\n'),
     ('- (id)computeCommandEncoder\n{ NATIVE_OBJECT_LOCK; \n',
      r'''- (void)presentDrawable:(id)drawable
{
	sweet_trace("cb %p presentDrawable: %p", self, drawable);
	struct objc_super sup = { self, [SweetNativeMetalCommandBuffer superclass] };
	((void (*)(struct objc_super *, SEL, id))objc_msgSendSuper)(&sup, _cmd, drawable);
}

- (id)computeCommandEncoder
{ NATIVE_OBJECT_LOCK;
	sweet_trace("cb %p computeCommandEncoder", self);
'''),
     ('- (id)renderCommandEncoderWithDescriptor:(id)descriptor\n{ NATIVE_OBJECT_LOCK; \n',
      r'''- (id)renderCommandEncoderWithDescriptor:(id)descriptor
{ NATIVE_OBJECT_LOCK;
	if (sweet_trace_enabled()) {
		MTLRenderPassColorAttachmentDescriptor *a0 =
		    [[(MTLRenderPassDescriptor *)descriptor colorAttachments] objectAtIndexedSubscript:0];
		id<MTLTexture> t = [a0 texture];
		id<MTLTexture> rt = [a0 resolveTexture];
		sweet_trace("cb %p renderCommandEncoder: color0 %p %lux%lu fmt %lu samples %lu load %lu store %lu depth %p "
		            "resolve %p %lux%lu fmt %lu level %lu surface %p",
		            self, t, (unsigned long)(t ? [t width] : 0), (unsigned long)(t ? [t height] : 0),
		            (unsigned long)(t ? [t pixelFormat] : 0), (unsigned long)(t ? [t sampleCount] : 0),
		            (unsigned long)[a0 loadAction], (unsigned long)[a0 storeAction],
		            [[(MTLRenderPassDescriptor *)descriptor depthAttachment] texture],
		            rt, (unsigned long)(rt ? [rt width] : 0), (unsigned long)(rt ? [rt height] : 0),
		            (unsigned long)(rt ? [rt pixelFormat] : 0), (unsigned long)[a0 resolveLevel],
		            rt != nil && [(id)rt respondsToSelector:@selector(iosurface)] ? (void *)[(id)rt iosurface] : NULL);
	}
'''),
     ('\tid _resolve[8];\n', '\tid _resolve[8];\n\tunsigned _sweetTraceDraws;\n'),
     ('      baseInstance:(NSUInteger)baseInstance\n{ NATIVE_OBJECT_LOCK; \n\tSweetNativeMetalWork *work = [[SweetNativeMetalWork alloc] init];\n',
      '      baseInstance:(NSUInteger)baseInstance\n{ NATIVE_OBJECT_LOCK; \n\tSweetNativeMetalWork *work = [[SweetNativeMetalWork alloc] init];\n'
      '\t_sweetTraceDraws++;\n'),
     ('- (void)endEncoding\n{ NATIVE_OBJECT_LOCK; \n    if(_nativeClearMask',
      '- (void)endEncoding\n{ NATIVE_OBJECT_LOCK; \n'
      '    sweet_trace("render encoder %p endEncoding: %u draw calls, clear mask %#x, pipeline %p", self, _sweetTraceDraws,\n'
      '                _nativeClearMask, _pipeline);\n'
      '    if(_nativeClearMask'),
     ('- (void)endEncoding\n{ NATIVE_OBJECT_LOCK; \n\t[super endEncoding];\n}',
      '- (void)endEncoding\n{ NATIVE_OBJECT_LOCK; \n\tsweet_trace("compute encoder %p endEncoding", self);\n\t[super endEncoding];\n}'),
     # Cull mode, winding and fill mode go to the draw (backend: rasterizer variants)
     # instead of failing the command buffer; and a failed command buffer now says why.
     ('    unsigned nativeScissor[4], nativeFlags;\n',
      '    unsigned nativeScissor[4], nativeFlags;\n    unsigned nativeCull, nativeWinding, nativeFill;\n'),
     ('    unsigned _nativeScissor[4], _nativeFlags;\n',
      '    unsigned _nativeScissor[4], _nativeFlags;\n    unsigned _nativeCull, _nativeWinding, _nativeFill;\n'),
     ('        .native_flags=work->nativeFlags,\n',
      '        .native_flags=work->nativeFlags,\n'
      '        .native_cull=work->nativeCull,.native_winding=work->nativeWinding,.native_fill=work->nativeFill,\n'),
     ('    work->nativeFlags=_nativeFlags;\n',
      '    work->nativeFlags=_nativeFlags;\n'
      '    work->nativeCull=_nativeCull;work->nativeWinding=_nativeWinding;work->nativeFill=_nativeFill;\n'),
     ('- (void)setCullMode:(NSUInteger)mode { NATIVE_OBJECT_LOCK; if(mode)[_commandBuffer failWith:"interface: culling is not implemented"];}\n'
      '- (void)setFrontFacingWinding:(NSUInteger)mode { NATIVE_OBJECT_LOCK; if(mode)[_commandBuffer failWith:"interface: non-default winding is not implemented"];}\n'
      '- (void)setTriangleFillMode:(NSUInteger)mode { NATIVE_OBJECT_LOCK; if(mode)[_commandBuffer failWith:"interface: wireframe is not implemented"];}\n',
      r'''/* MTLCullMode none 0 / front 1 / back 2, MTLWinding clockwise 0 / counter-clockwise 1,
 * MTLTriangleFillMode fill 0 / lines 1: kept for the draws that follow. */
- (void)setCullMode:(NSUInteger)mode
{ NATIVE_OBJECT_LOCK;
	if (mode > 2) { [_commandBuffer failWith:"interface: unknown cull mode"]; return; }
	_nativeCull = (unsigned)mode;
	RW_ONCE("setCullMode: %lu honoured (rasterizer variant per draw)\n", (unsigned long)mode);
}
- (void)setFrontFacingWinding:(NSUInteger)mode { NATIVE_OBJECT_LOCK; _nativeWinding = mode ? 1 : 0; }
- (void)setTriangleFillMode:(NSUInteger)mode
{ NATIVE_OBJECT_LOCK;
	_nativeFill = mode ? 1 : 0;
	if (mode)
		RW_ONCE("setTriangleFillMode: %lu drawn as lines\n", (unsigned long)mode);
}
'''),
     ('- (void)failWith:(const char *)reason\n{ NATIVE_OBJECT_LOCK; \n',
      '- (void)failWith:(const char *)reason\n{ NATIVE_OBJECT_LOCK; \n'
      '\tstatic unsigned told;\n'
      '\tif (__atomic_add_fetch(&told, 1, __ATOMIC_RELAXED) <= 16)\n'
      '\t\trw_print("command buffer %p failed: %s\\n", self, reason);\n'))

# Draw log: which texture object (a view names its parent) and which level, so a pass that
# samples the texture it renders into can be told from one that ping-pongs.
edit('userland/src/SweetNativeDrawLog.inc',
     ('\t\tsnprintf(rt + at, sizeof(rt) - at, "%s%u:%ux%u", i ? "," : "",\n'
      '\t\t         t ? (unsigned)[t pixelFormat] : 0, t ? (unsigned)[t width] : 0,\n'
      '\t\t         t ? (unsigned)[t height] : 0);',
      '\t\tid p = t && [t respondsToSelector:@selector(parentTexture)] ? [t parentTexture] : nil;\n'
      '\t\tsnprintf(rt + at, sizeof(rt) - at, "%s%u:%ux%u#%04x/L%u", i ? "," : "",\n'
      '\t\t         t ? (unsigned)[t pixelFormat] : 0, t ? (unsigned)[t width] : 0,\n'
      '\t\t         t ? (unsigned)[t height] : 0,\n'
      '\t\t         (unsigned)(((uintptr_t)(p ? p : t) >> 4) & 0xffff),\n'
      '\t\t         p ? (unsigned)[t parentRelativeLevel] : 0);'),
     ('\t\tsnprintf(tx + at, sizeof(tx) - at, "%s%u:%u:%ux%u", at ? "," : "", i,\n'
      '\t\t         (unsigned)[t pixelFormat], (unsigned)[t width], (unsigned)[t height]);',
      '\t\tid p = [t respondsToSelector:@selector(parentTexture)] ? [t parentTexture] : nil;\n'
      '\t\tsnprintf(tx + at, sizeof(tx) - at, "%s%u:%u:%ux%u#%04x/L%u+%u", at ? "," : "", i,\n'
      '\t\t         (unsigned)[t pixelFormat], (unsigned)[t width], (unsigned)[t height],\n'
      '\t\t         (unsigned)(((uintptr_t)(p ? p : t) >> 4) & 0xffff),\n'
      '\t\t         p ? (unsigned)[t parentRelativeLevel] : 0, (unsigned)[t mipmapLevelCount]);'),
     # GLASSSTAT (Liquid Glass vanishing on the A71, no draw ever fails): once a second, the
     # draws this process executed and how many were CoreAnimation's glass and blur passes.
     # Always on, no file to touch (a delayed package corrupted the catalog once), one line
     # per second only while something draws. It tells the two causes apart: CoreAnimation
     # stops sending glass draws (its own decision, e.g. late frames) or keeps sending them
     # (then the picture is wrong here).
     ('static void\nnative_drawlog_draw(unsigned seq,',
      '''static bool
native_wall_texture_event(const char *operation, id texture, const void *caller)
{
	if (texture == nil)
		return false;
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-drawlog-metadata-only", F_OK) == 0;
	});
	if (!enabled || [texture width] < 600 || [texture height] < 1200 || [texture usage] != 1)
		return false;
	Dl_info image = {0};
	const bool found = dladdr(caller, &image) && image.dli_fname != NULL &&
	                   image.dli_fbase != NULL;
	const char *base = found ? strrchr(image.dli_fname, '/') : NULL;
	const char *image_name = !found ? "unknown" : base ? base + 1 : image.dli_fname;
	const uintptr_t offset = found ? (uintptr_t)caller - (uintptr_t)image.dli_fbase : 0;
	static unsigned events;
	if (__atomic_fetch_add(&events, 1, __ATOMIC_RELAXED) < 64)
		fprintf(stderr, "SweetNativeMetal: WALLTEX %s %p %ux%u caller %s+0x%lx\\n",
		        operation, (void *)texture, (unsigned)[texture width], (unsigned)[texture height],
		        image_name, (unsigned long)offset);
	return !strcmp(image_name, "QuartzCore") && offset == 0x10af34 &&
	       !strcmp(operation, "upload");
}

/* Test only the adjacent opaque/source-over pair seen in the wallpaper trace. */
static bool
native_wall_skip_repeated_surface(const void *commands, const void *render,
                                  id const *colors, unsigned ncolors,
                                  id const *textures, unsigned ntextures,
                                  bool has_depth, unsigned count, unsigned flags,
                                  const float viewport[4], const unsigned scissor[4])
{
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-wallpaper-repeat-test", F_OK) == 0;
	});
	if (!enabled)
		return false;

	static _Thread_local const void *previous_commands;
	static _Thread_local uintptr_t previous_source;
	static _Thread_local uintptr_t previous_targets[2];
	const uintptr_t old_source = previous_source;
	previous_source = 0;
	if (has_depth || count != 6 || ncolors != 2 || ntextures <= 3 ||
	    colors[0] == nil || colors[1] == nil || textures[3] == nil)
		return false;

	id source = textures[3];
	id target = colors[0];
	if ([target width] != 828 || [target height] != 1792 ||
	    [source width] != 828 || [source height] != 1792 ||
	    ![source respondsToSelector:@selector(iosurface)] || [source iosurface] == NULL ||
	    ((flags & 1) && (viewport[0] || viewport[1] || viewport[2] != 828 ||
	                     viewport[3] != 1792)) ||
	    ((flags & 2) && (scissor[0] || scissor[1] || scissor[2] != 828 ||
	                     scissor[3] != 1792)))
		return false;

	pthread_mutex_lock(&native_drawlog_lock);
	const struct native_drawlog_name *name = native_drawlog_slot(render, false);
	const bool fixed = name != NULL && !strcmp(name->vfn, "fixed_vert_lph_spc") &&
	                   !strcmp(name->ffn, "fixed_frag_lph_cph");
	const bool opaque = fixed &&
		!strcmp(name->label, "com.apple.coreanimation.PBGRAXm_TimgA2Xhf_Ixrg");
	const bool source_over = fixed &&
		!strcmp(name->label, "com.apple.coreanimation.PBGRABsovXm_TimgA2Xhf_Isrc");
	pthread_mutex_unlock(&native_drawlog_lock);
	if (opaque) {
		previous_commands = commands;
		previous_source = (uintptr_t)source;
		previous_targets[0] = (uintptr_t)target;
		previous_targets[1] = (uintptr_t)colors[1];
	}
	if (!source_over || old_source != (uintptr_t)source || previous_commands != commands ||
	    previous_targets[0] != (uintptr_t)target || previous_targets[1] != (uintptr_t)colors[1])
		return false;

	static unsigned skipped;
	if (__atomic_fetch_add(&skipped, 1, __ATOMIC_RELAXED) < 8)
		fprintf(stderr, "SweetNativeMetal: skipped repeated wallpaper IOSurface %u\\n",
		        rwd_surface_id((void *)[source iosurface]));
	return true;
}

/* XRGALPHA (opt-in, /var/local/sweet-native-xrg-alpha-one, backboardd): CoreAnimation's
 * `_Ixrg` image shaders mean "this layer is opaque, ignore its alpha". Mercury's live
 * wallpaper IOSurface carries alpha 0..255 (WALLREGION, 2026-11-23), and here the Ixrg pass
 * wrote that alpha into the frame. Cover Sheet's next full-screen pass
 * (PBGRAXm_TimgBdsoA2Xhfn_Isrc, a 256x1 gradient) then showed through wherever the frame
 * alpha was low, and the home screen's source-over repeat of the same surface added it to
 * itself. Give such an IOSurface texture the Metal swizzle (r, g, b, one) once, the first
 * time CoreAnimation draws it as opaque. */
@interface NSObject (SweetNativeXrgMesa)
- (struct rwa_texture *)mesaTexture;
@end

static char native_xrg_done_key;

/* Called for every draw: marks the slot-3 texture of an _Ixrg draw for the backend
 * (rwa_texture_mark_opaque), so only that draw samples it with alpha 1; any other draw
 * clears the mark. native_xrg_clear() runs after the backend draw. */
static void
native_xrg_alpha_one(const void *render, id const *textures, unsigned ntextures)
{
	void rwa_texture_mark_opaque(struct rwa_texture *);
	void rwa_render_straight_alpha_next(bool);
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-wallpaper-depth", F_OK) == 0;
		if (enabled)
			fprintf(stderr, "SweetNativeMetal: XRGALPHA enabled: Ixrg passes alpha 1, depth pass straight alpha\\n");
	});
	if (!enabled)
		return;
	rwa_texture_mark_opaque(NULL);
	rwa_render_straight_alpha_next(false);
	if (ntextures <= 3 || textures[3] == nil)
		return;
	id source = textures[3];
	pthread_mutex_lock(&native_drawlog_lock);
	const struct native_drawlog_name *name = native_drawlog_slot(render, false);
	const size_t len = name != NULL ? strlen(name->label) : 0;
	const bool xrg = len > 5 && !strcmp(name->label + len - 5, "_Ixrg") &&
	                 !strncmp(name->label, "com.apple.coreanimation.", 24);
	/* The depth-effect pass: the same live wallpaper surface again with the plain source-over
	 * image shader, after the clock. Mercury's rgb is not premultiplied and its alpha is an
	 * occlusion mask (rasterizeBackgroundFragment: alpha = wantsOcclusion ? 0 : 1), so this
	 * pass blends rgb*a + dst*(1-a): discs over the clock, nothing added twice. */
	/* any source-over image pass (transitions use variants, e.g. _Xhfn_) */
	const bool over = name != NULL && len > 5 &&
		!strncmp(name->label, "com.apple.coreanimation.PBGRABsovXm_Timg", 40) &&
		!strcmp(name->label + len - 5, "_Isrc");
	pthread_mutex_unlock(&native_drawlog_lock);
	if ((!xrg && !over) || ![source respondsToSelector:@selector(iosurface)] ||
	    [source iosurface] == NULL || ![source respondsToSelector:@selector(mesaTexture)])
		return;
	const unsigned fmt = (unsigned)[source pixelFormat];
	if (fmt != 80 && fmt != 81)
		return;
	if (over) {
		int rwd_surface_straight_alpha(void *);
		static char straight_key;   /* per texture: the surface's tag, read once */
		NSNumber *straight = objc_getAssociatedObject(source, &straight_key);
		if (straight == nil) {
			straight = rwd_surface_straight_alpha((void *)[source iosurface]) ? @YES : @NO;
			objc_setAssociatedObject(source, &straight_key, straight, OBJC_ASSOCIATION_RETAIN);
		}
		if (objc_getAssociatedObject(source, &native_xrg_done_key) != nil || [straight boolValue]) {
			rwa_render_straight_alpha_next(true);
			static unsigned told_depth;
			if (__atomic_fetch_add(&told_depth, 1, __ATOMIC_RELAXED) < 8)
				fprintf(stderr, "SweetNativeMetal: XRGALPHA depth pass IOSurface %u straight alpha\\n",
				        rwd_surface_id((void *)[source iosurface]));
		}
		return;
	}
	rwa_texture_mark_opaque([source mesaTexture]);
	if (objc_getAssociatedObject(source, &native_xrg_done_key) != nil)
		return;
	objc_setAssociatedObject(source, &native_xrg_done_key, @YES, OBJC_ASSOCIATION_RETAIN);
	static unsigned told;
	if (__atomic_fetch_add(&told, 1, __ATOMIC_RELAXED) < 16)
		fprintf(stderr, "SweetNativeMetal: XRGALPHA IOSurface %u texture %p %ux%u opaque in Ixrg draws\\n",
		        rwd_surface_id((void *)[source iosurface]), (void *)source,
		        (unsigned)[source width], (unsigned)[source height]);
}

/* MERCURYOCCL (opt-in, /var/local/sweet-native-mercury-occl, MercuryPosterExtension): for
 * each draw of space::rasterize*Fragment, the SpaceCommonUniforms flags isBackgroundPass
 * (byte 484) and wantsOcclusion (byte 485) of fragment buffer 0, and the colour target's
 * IOSurface, size and format. The background writes alpha = wantsOcclusion ? 0 : 1, and
 * backboardd draws the same surface opaque and again source-over (depth effect over the
 * clock), so which render carries the occlusion alpha decides the composite. No readback. */
static void
native_mercury_occl_trace(const void *render, id const *colors, unsigned ncolors,
                          id const *fbufs, const size_t *foffs, unsigned nfb)
{
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "MercuryPosterExtension") &&
		          access("/var/local/sweet-native-mercury-occl", F_OK) == 0;
		if (enabled)
			fprintf(stderr, "SweetNativeMetal: MERCURYOCCL enabled\\n");
	});
	if (!enabled || nfb == 0 || fbufs[0] == nil)
		return;
	char ffn[48] = "";
	pthread_mutex_lock(&native_drawlog_lock);
	const struct native_drawlog_name *name = native_drawlog_slot(render, false);
	if (name != NULL)
		memcpy(ffn, name->ffn, sizeof(ffn));
	pthread_mutex_unlock(&native_drawlog_lock);
	ffn[sizeof(ffn) - 1] = 0;
	if (strncmp(ffn, "space::rasterize", 16) != 0)
		return;
	static unsigned told;
	if (__atomic_fetch_add(&told, 1, __ATOMIC_RELAXED) >= 400)
		return;
	const uint8_t *base = (const uint8_t *)[fbufs[0] contents];
	const size_t len = (size_t)[fbufs[0] length], off = (size_t)foffs[0];
	int bg = -1, occl = -1;
	unsigned sw = 0, sh = 0;
	if (base != NULL && off + 486 <= len) {
		bg = base[off + 484];
		occl = base[off + 485];
		sw = (unsigned)base[off + 480] | (unsigned)base[off + 481] << 8;
		sh = (unsigned)base[off + 482] | (unsigned)base[off + 483] << 8;
	}
	id rt = ncolors ? colors[0] : nil;
	void *surface = rt != nil && [rt respondsToSelector:@selector(iosurface)] ? (void *)[rt iosurface] : NULL;
	fprintf(stderr, "SweetNativeMetal: MERCURYOCCL %s bg=%d occl=%d screen=%ux%u rt %p %ux%u fmt %u samples %u IOSurface %u\\n",
	        ffn, bg, occl, sw, sh, (void *)rt, rt ? (unsigned)[rt width] : 0, rt ? (unsigned)[rt height] : 0,
	        rt ? (unsigned)[rt pixelFormat] : 0, rt ? (unsigned)[rt sampleCount] : 0, rwd_surface_id(surface));
}

/* GLASSU (opt-in, /var/local/sweet-native-glass-uniforms, backboardd): for CoreAnimation's glass passes
 * Sample background and foreground independently through the whole interaction. The startup burst
 * used to consume the entire trace before the user could swipe. No texture readback here. */
static void
native_glass_uniform_trace(const void *render, id const *colors, unsigned ncolors, id const *fbufs, const size_t *foffs,
                           unsigned nfb, id const *textures, unsigned ntextures)
{
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-glass-uniforms", F_OK) == 0;
		if (enabled)
			fprintf(stderr, "SweetNativeMetal: GLASSU enabled\\n");
	});
	if (!enabled || nfb < 2 || fbufs[1] == nil)
		return;
	char ffn[48] = "";
	pthread_mutex_lock(&native_drawlog_lock);
	const struct native_drawlog_name *name = native_drawlog_slot(render, false);
	if (name != NULL)
		memcpy(ffn, name->ffn, sizeof(ffn));
	pthread_mutex_unlock(&native_drawlog_lock);
	ffn[sizeof(ffn) - 1] = 0;
	if (strncmp(ffn, "glass_", 6) != 0)
		return;
	const uint8_t *base = (const uint8_t *)[fbufs[1] contents];
	const size_t len = (size_t)[fbufs[1] length], off = foffs[1];
	if (base == NULL || off > len || len - off < 272)
		return;
	struct timespec now;
	if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
		return;
	const unsigned stage = strncmp(ffn, "glass_foreground", 16) == 0;
	const uint64_t tick = (uint64_t)now.tv_sec + 1;
	static uint64_t last_tick[2];
	uint64_t last = __atomic_load_n(&last_tick[stage], __ATOMIC_RELAXED);
	if (last >= tick || !__atomic_compare_exchange_n(&last_tick[stage], &last, tick, false,
	                                                __ATOMIC_RELAXED, __ATOMIC_RELAXED))
		return;
	static unsigned sequence;
	const unsigned n = __atomic_fetch_add(&sequence, 1, __ATOMIC_RELAXED);
	id rt = ncolors ? colors[0] : nil;
	id t3 = ntextures > 3 ? textures[3] : nil, t4 = ntextures > 4 ? textures[4] : nil;
	fprintf(stderr, "SweetNativeMetal: GLASSU %u %s rt %ux%u fmt %u colors %u buf %zu@%zu src %ux%u fmt %u lv %u sdf %ux%u fmt %u\\n",
	        n, ffn, (unsigned)[rt width], (unsigned)[rt height], (unsigned)[rt pixelFormat], ncolors, len, off,
	        t3 ? (unsigned)[t3 width] : 0, t3 ? (unsigned)[t3 height] : 0, t3 ? (unsigned)[t3 pixelFormat] : 0,
	        t3 ? (unsigned)[t3 mipmapLevelCount] : 0, t4 ? (unsigned)[t4 width] : 0, t4 ? (unsigned)[t4 height] : 0,
	        t4 ? (unsigned)[t4 pixelFormat] : 0);
	const float *f = (const float *)(base + off);
	for (unsigned row = 0; row < 4; row++) {
		char line[400];
		int at = snprintf(line, sizeof(line), "SweetNativeMetal: GLASSU %u f%u:", n, row * 17);
		for (unsigned k = 0; k < 17 && at > 0 && (size_t)at < sizeof(line); k++)
			at += snprintf(line + at, sizeof(line) - at, " %.4g", f[row * 17 + k]);
		fprintf(stderr, "%s\\n", line);
	}
}

/* Opt-in paired readback. Keep it separate from GLASSU since readback can
 * synchronize GPU work and change the timing of the symptom. */
static bool
native_glass_pixels_should_sample(const void *render)
{
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-glass-pixels", F_OK) == 0;
	});
	if (!enabled)
		return false;
	char ffn[48] = "";
	pthread_mutex_lock(&native_drawlog_lock);
	const struct native_drawlog_name *name = native_drawlog_slot(render, false);
	if (name != NULL)
		memcpy(ffn, name->ffn, sizeof(ffn) - 1);
	pthread_mutex_unlock(&native_drawlog_lock);
	if (strcmp(ffn, "glass_background_no_bleed_lph"))
		return false;
	struct timespec now;
	if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
		return false;
	static uint64_t last_tick;
	const uint64_t tick = (uint64_t)now.tv_sec / 3 + 1;
	uint64_t last = __atomic_load_n(&last_tick, __ATOMIC_RELAXED);
	return last < tick && __atomic_compare_exchange_n(&last_tick, &last, tick, false,
	                                                 __ATOMIC_RELAXED, __ATOMIC_RELAXED);
}

static void
native_glass_pixel_region(const char *phase, const char *name, id texture,
                          unsigned x, unsigned y, unsigned width, unsigned height)
{
	const unsigned tw = (unsigned)[texture width], th = (unsigned)[texture height];
	const unsigned fmt = (unsigned)[texture pixelFormat];
	if (x >= tw || y >= th || (fmt != 80 && fmt != 81 && fmt != 115))
		return;
	const unsigned w = MIN(width, tw - x), h = MIN(height, th - y);
	if (!w || !h)
		return;
	const unsigned stride = fmt == 115 ? 8 : 4;
	const size_t count = (size_t)w * h;
	if (count > 1536u * 1024u) {
		fprintf(stderr, "SweetNativeMetal: GLASSPX %s %s region too large %ux%u\\n", phase, name, w, h);
		return;
	}
	uint8_t *pixels = calloc(count, stride);
	if (pixels == NULL)
		return;
	[texture getBytes:pixels bytesPerRow:w * stride
	       fromRegion:MTLRegionMake2D(x, y, w, h) mipmapLevel:0];
	uint32_t hash = 2166136261u;
	for (size_t i = 0; i < count * stride; i++)
		hash = (hash ^ pixels[i]) * 16777619u;
	unsigned inside = 0;
	if (fmt == 115 && !strcmp(name, "sdf")) {
		const uint16_t *half = (const uint16_t *)pixels;
		for (size_t i = 0; i < count; i++) {
			const uint16_t distance = half[i * 4], alpha = half[i * 4 + 3];
			inside += distance > 0x8000 && distance < 0xfc00 && alpha > 0 && alpha <= 0x3c00;
		}
	}
	uint32_t first = 0, second = 0;
	memcpy(&first, pixels, 4);
	if (stride == 8)
		memcpy(&second, pixels + 4, 4);
	fprintf(stderr, "SweetNativeMetal: GLASSPX %s %s %p fmt %u region %u,%u %ux%u hash %08x first %08x %08x inside %u\\n",
	        phase, name, (void *)texture, fmt, x, y, w, h, hash, first, second, inside);
	free(pixels);
}

static void
native_glass_pixels(const char *phase, id const *colors, unsigned ncolors,
                    id const *textures, unsigned ntextures, const unsigned *scissor, unsigned flags)
{
	if (!strcmp(phase, "before")) {
		for (unsigned i = 3; i < ntextures && i <= 4; i++) {
			id texture = textures[i];
			native_glass_pixel_region(phase, i == 3 ? "source" : "sdf", texture, 0, 0,
			                          (unsigned)[texture width], (unsigned)[texture height]);
		}
	}
	for (unsigned i = 0; i < ncolors && i < 2; i++) {
		id texture = colors[i];
		const bool clipped = (flags & 2) != 0;
		native_glass_pixel_region(phase, i == 0 ? "color0" : "color1", texture,
		                          clipped ? scissor[0] : 0, clipped ? scissor[1] : 0,
		                          clipped ? scissor[2] : (unsigned)[texture width],
		                          clipped ? scissor[3] : (unsigned)[texture height]);
	}
}

/* VBLUR (opt-in, /var/local/sweet-native-vblur, backboardd): CoreAnimation's variable blur
 * (fragment function variable_blur*), used by the iOS 26 scroll-edge blur under the title bar.
 * Owner photos 2026-11-23: that blur is uniformly strong and ends in a hard line instead of fading.
 * variable_blur_frag picks a source level from max_blur * mask_texture.a (mask in slot 4), so this logs
 * fragment buffer 1 as 16 floats, every bound texture (size, format, levels, samples), the render target
 * and, for at most 12 draws (one per 2 s), the mask read back as mean alpha in 16 horizontal bands.
 * 64 draws max. */
static void
native_vblur_trace(const void *render, id const *colors, unsigned ncolors, id const *fbufs,
                   const size_t *foffs, unsigned nfb, id const *textures, unsigned ntextures,
                   id const *vbufs, const size_t *voffs, unsigned nvb, unsigned vstart, unsigned vcount,
                   bool indexed)
{
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-vblur", F_OK) == 0;
		if (enabled)
			fprintf(stderr, "SweetNativeMetal: VBLUR enabled\\n");
	});
	if (!enabled)
		return;
	char ffn[48] = "", label[96] = "";
	pthread_mutex_lock(&native_drawlog_lock);
	const struct native_drawlog_name *name = native_drawlog_slot(render, false);
	if (name != NULL) {
		memcpy(ffn, name->ffn, sizeof(ffn));
		strlcpy(label, name->label, sizeof(label));
	}
	pthread_mutex_unlock(&native_drawlog_lock);
	ffn[sizeof(ffn) - 1] = 0;
	if (strncmp(ffn, "variable_blur", 13) != 0)
		return;
	/* The mip chain (variable_blur_downsample*) runs every frame on the lock screen and used up a
	 * shared limit of 64 before any other variable_blur draw (2026-11-24): separate limits. */
	static unsigned told, told_down;
	const bool down = strstr(ffn, "downsample") != NULL;
	if (down && __atomic_fetch_add(&told_down, 1, __ATOMIC_RELAXED) >= 8)
		return;
	const unsigned n = down ? 1000 + told_down : __atomic_fetch_add(&told, 1, __ATOMIC_RELAXED);
	if (!down && n >= 64)
		return;
	id rt = ncolors ? colors[0] : nil;
	char line[900];
	int at = snprintf(line, sizeof(line), "SweetNativeMetal: VBLUR %u %s %s rt %ux%u fmt %u tex", n, ffn, label,
	                  rt ? (unsigned)[rt width] : 0, rt ? (unsigned)[rt height] : 0,
	                  rt ? (unsigned)[rt pixelFormat] : 0);
	for (unsigned k = 0; k < ntextures && k < 8 && at > 0 && (size_t)at < sizeof(line); k++) {
		id t = textures[k];
		if (t == nil)
			at += snprintf(line + at, sizeof(line) - at, " %u:-", k);
		else
			at += snprintf(line + at, sizeof(line) - at, " %u:%ux%u/f%u/l%u/s%u", k, (unsigned)[t width],
			               (unsigned)[t height], (unsigned)[t pixelFormat], (unsigned)[t mipmapLevelCount],
			               (unsigned)[t sampleCount]);
	}
	fprintf(stderr, "%s\\n", line);
	/* The mask coordinate is texcoord1 = in.texcoord1 * texmat[1].xy + texmat[1].zw (vertex
	 * buffer 3 holds texmat, declared float4 but read as two); vertex inputs 0-2 come from
	 * the vertex buffers. First 6 main-pass draws: 32 floats of vertex buffers 0-3. */
	if (!down && n < 6) {
		fprintf(stderr, "SweetNativeMetal: VBLUR %u verts start %u count %u indexed %d vbufs %u\\n", n, vstart,
		        vcount, (int)indexed, nvb);
		for (unsigned b = 0; b < nvb && b < 4; b++) {
			if (vbufs[b] == nil) {
				fprintf(stderr, "SweetNativeMetal: VBLUR %u vb%u -\\n", n, b);
				continue;
			}
			const uint8_t *vbase = (const uint8_t *)[vbufs[b] contents];
			const size_t vlen = (size_t)[vbufs[b] length], voff = voffs[b];
			at = snprintf(line, sizeof(line), "SweetNativeMetal: VBLUR %u vb%u (%zu@%zu):", n, b, vlen, voff);
			for (unsigned k = 0; vbase != NULL && k < 32 && voff + (k + 1) * 4 <= vlen && at > 0 &&
			                     (size_t)at < sizeof(line); k++) {
				float v;
				memcpy(&v, vbase + voff + k * 4, sizeof(v));
				at += snprintf(line + at, sizeof(line) - at, " %.4g", v);
			}
			fprintf(stderr, "%s\\n", line);
		}
	}
	if (nfb > 1 && fbufs[1] != nil) {
		const uint8_t *base = (const uint8_t *)[fbufs[1] contents];
		const size_t len = (size_t)[fbufs[1] length], off = foffs[1];
		unsigned nf = 0;
		if (base != NULL && off < len)
			nf = (len - off) / 4 < 16 ? (unsigned)((len - off) / 4) : 16;
		at = snprintf(line, sizeof(line), "SweetNativeMetal: VBLUR %u u1 (%zu@%zu):", n, len, off);
		for (unsigned k = 0; k < nf && at > 0 && (size_t)at < sizeof(line); k++) {
			float v;
			memcpy(&v, base + off + k * 4, sizeof(v));
			at += snprintf(line + at, sizeof(line) - at, " %.4g", v);
		}
		fprintf(stderr, "%s\\n", line);
	}
	/* VBLUR sharpness: the scroll-edge blur keeps a hard line where its opacity cuts off,
	 * so its low-LOD image is still soft. For the first 4 main-pass draws, each level of the
	 * source chain (slot 3) is read back and its mean absolute neighbour difference (x and
	 * y, BGR) is logged: a level 0 as soft as level 1 means the chain build is wrong. */
	if (!down && n < 4 && ntextures > 3 && textures[3] != nil && [textures[3] sampleCount] <= 1) {
		id src = textures[3];
		const unsigned sfmt = (unsigned)[src pixelFormat];
		if (sfmt == 80 || sfmt == 81 || sfmt == 70 || sfmt == 71) {
			unsigned slevels = (unsigned)[src mipmapLevelCount];
			slevels = slevels == 0 ? 1 : slevels > 4 ? 4 : slevels;
			at = snprintf(line, sizeof(line), "SweetNativeMetal: VBLUR %u source sharpness (mean |dx|,|dy| per level):", n);
			for (unsigned l = 0; l < slevels; l++) {
				unsigned sw = (unsigned)[src width] >> l, sh = (unsigned)[src height] >> l;
				sw = sw ? sw : 1;
				sh = sh ? sh : 1;
				uint8_t *sp = malloc((size_t)sw * sh * 4);
				if (sp == NULL)
					break;
				[src getBytes:sp bytesPerRow:sw * 4 fromRegion:MTLRegionMake2D(0, 0, sw, sh) mipmapLevel:l];
				uint64_t gx = 0, gy = 0, cx = 0, cy = 0;
				for (unsigned y = 0; y < sh; y++)
					for (unsigned x = 0; x < sw; x++)
						for (unsigned k = 0; k < 3; k++) {
							const int v = sp[((size_t)y * sw + x) * 4 + k];
							if (x + 1 < sw) {
								gx += (uint64_t)abs(v - sp[((size_t)y * sw + x + 1) * 4 + k]);
								cx++;
							}
							if (y + 1 < sh) {
								gy += (uint64_t)abs(v - sp[((size_t)(y + 1) * sw + x) * 4 + k]);
								cy++;
							}
						}
				free(sp);
				if (at > 0 && (size_t)at < sizeof(line))
					at += snprintf(line + at, sizeof(line) - at, " L%u %ux%u %.2f,%.2f", l, sw, sh,
					               cx ? (double)gx / cx : 0.0, cy ? (double)gy / cy : 0.0);
			}
			fprintf(stderr, "%s\\n", line);
		}
	}
	id mask = ntextures > 4 ? textures[4] : nil;
	if (mask == nil || [mask sampleCount] > 1)
		return;
	const unsigned fmt = (unsigned)[mask pixelFormat];
	const unsigned bpp = (fmt == 1 || fmt == 10) ? 1 : (fmt == 70 || fmt == 71 || fmt == 80 || fmt == 81) ? 4 : 0;
	if (bpp == 0) {
		fprintf(stderr, "SweetNativeMetal: VBLUR %u mask format %u not read\\n", n, fmt);
		return;
	}
	static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
	static uint64_t next_ms;
	static unsigned reads;
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	const uint64_t ms = (uint64_t)now.tv_sec * 1000 + (uint64_t)now.tv_nsec / 1000000;
	pthread_mutex_lock(&lock);
	const bool go = reads < 12 && ms >= next_ms;
	if (go) {
		reads++;
		next_ms = ms + 2000;
	}
	pthread_mutex_unlock(&lock);
	if (!go)
		return;
	const unsigned w = (unsigned)[mask width], h = (unsigned)[mask height];
	if (w == 0 || h == 0 || (size_t)w * h > 4096u * 4096u)
		return;
	uint8_t *px = malloc((size_t)w * h * bpp);
	if (px == NULL)
		return;
	memset(px, 0xee, (size_t)w * h * bpp);
	[mask getBytes:px bytesPerRow:w * bpp fromRegion:MTLRegionMake2D(0, 0, w, h) mipmapLevel:0];
	at = snprintf(line, sizeof(line), "SweetNativeMetal: VBLUR %u mask %ux%u fmt %u alpha by band (top..bottom):",
	              n, w, h, fmt);
	const unsigned bands = h < 16 ? h : 16, step = w > 64 ? w / 64 : 1;
	for (unsigned b = 0; b < bands && at > 0 && (size_t)at < sizeof(line); b++) {
		const unsigned y0 = h * b / bands, y1 = h * (b + 1) / bands;
		uint64_t sum = 0;
		size_t cnt = 0;
		for (unsigned y = y0; y < y1; y++)
			for (unsigned x = 0; x < w; x += step, cnt++)
				sum += px[((size_t)y * w + x) * bpp + (bpp - 1)];
		at += snprintf(line + at, sizeof(line) - at, " %u", (unsigned)(cnt ? sum / cnt : 0));
	}
	fprintf(stderr, "%s\\n", line);
	free(px);
}

/* VBLURMASK (opt-in, /var/local/sweet-native-vblur-mask-copy, backboardd): every draw of
 * variable_blur_frag* gets, in slot 4 (mask_texture), a plain shared texture this driver makes and
 * fills with the bytes read back from CoreAnimation's mask. The scroll-edge blur stays uniformly
 * strong with a hard edge although the mask read back from the CPU fades (2026-11-24) and every
 * other input checks out (VBLUR/VDESC). If the copy fixes it, the original mask texture is what the
 * GPU sees wrong. The copy is remade only when the source or its bytes change. */
static void
native_vblur_mask_copy(const void *render, id *textures, unsigned ntextures)
{
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-vblur-mask-copy", F_OK) == 0;
		if (enabled)
			fprintf(stderr, "SweetNativeMetal: VBLURMASK copy enabled\\n");
	});
	if (!enabled || ntextures <= 4 || textures[4] == nil)
		return;
	char ffn[48] = "";
	pthread_mutex_lock(&native_drawlog_lock);
	const struct native_drawlog_name *name = native_drawlog_slot(render, false);
	if (name != NULL)
		memcpy(ffn, name->ffn, sizeof(ffn));
	pthread_mutex_unlock(&native_drawlog_lock);
	ffn[sizeof(ffn) - 1] = 0;
	if (strncmp(ffn, "variable_blur_frag", 18) != 0)
		return;
	id mask = textures[4];
	const unsigned fmt = (unsigned)[mask pixelFormat];
	if ([mask sampleCount] > 1 || (fmt != 70 && fmt != 71 && fmt != 80 && fmt != 81))
		return;
	const unsigned w = (unsigned)[mask width], h = (unsigned)[mask height];
	if (w == 0 || h == 0 || (size_t)w * h > 1048576)
		return;
	uint8_t *px = malloc((size_t)w * h * 4);
	if (px == NULL)
		return;
	[mask getBytes:px bytesPerRow:w * 4 fromRegion:MTLRegionMake2D(0, 0, w, h) mipmapLevel:0];
	uint64_t hash = 1469598103934665603ull;
	for (size_t i = 0; i < (size_t)w * h * 4; i++)
		hash = (hash ^ px[i]) * 1099511628211ull;
	static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
	static void *last_src;
	static uint64_t last_hash;
	static id last_copy;
	static unsigned made;
	pthread_mutex_lock(&lock);
	if (last_copy == nil || last_src != (void *)mask || last_hash != hash) {
		MTLTextureDescriptor *desc =
		    [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:(MTLPixelFormat)fmt width:w height:h
		                                                   mipmapped:NO];
		[desc setUsage:MTLTextureUsageShaderRead];
		[desc setStorageMode:MTLStorageModeShared];
		id copy = [[mask device] newTextureWithDescriptor:desc];
		if (copy != nil) {
			[copy replaceRegion:MTLRegionMake2D(0, 0, w, h) mipmapLevel:0 withBytes:px bytesPerRow:w * 4];
			[last_copy release];
			last_copy = copy;
			last_src = (void *)mask;
			last_hash = hash;
			if (made++ < 8) {
				void *surface = [mask respondsToSelector:@selector(iosurface)] ? (void *)[mask iosurface] : NULL;
				fprintf(stderr, "SweetNativeMetal: VBLURMASK copy %u of mask %p %ux%u fmt %u storage %lu usage %#lx "
				        "iosurface %u levels %u\\n", made, (void *)mask, w, h, fmt,
				        (unsigned long)[mask storageMode], (unsigned long)[mask usage], rwd_surface_id(surface),
				        (unsigned)[mask mipmapLevelCount]);
			}
		}
	}
	id use = [last_copy retain];
	pthread_mutex_unlock(&lock);
	free(px);
	if (use == nil)
		return;
	[textures[4] release];
	textures[4] = use;
}

#include <errno.h>
#include <fcntl.h>
/* VBCAP (opt-in, /var/local/sweet-native-vblur-capture, backboardd): the inputs of ONE
 * variable_blur_frag* draw on a target at least 100x100, including one-column
 * gradient masks, written to the pre-created /var/local/vblur-capture.bin (0666;
 * backboardd runs as mobile), to be replayed offline on softpipe through the same backend
 * (air_metal.c) and compared with the phone. Layout, little-endian u32 unless noted:
 *   "VBCAP1\0\0", rt w h fmt, primitive vstart vcount baseVertex indexType nindices,
 *   index bytes, then for vertex buffers 1 2 3: index, length, bytes (from the offset),
 *   for fragment buffers 1 5 6: index, length, bytes, then textures 3 and 4: slot w h fmt
 *   levels, each level w>>l * h>>l * 4 bytes. Once per process. */
static void
native_vblur_capture(const void *render, id const *colors, unsigned ncolors, id const *fbufs,
                     const size_t *foffs, unsigned nfb, id const *textures, unsigned ntextures,
                     id const *vbufs, const size_t *voffs, unsigned nvb, unsigned primitive,
                     unsigned vstart, unsigned vcount, int base_vertex, id index_buffer,
                     unsigned index_type, size_t index_offset)
{
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-vblur-capture", F_OK) == 0;
		if (enabled)
			fprintf(stderr, "SweetNativeMetal: VBCAP armed\\n");
	});
	static int done;
	if (!enabled || __atomic_load_n(&done, __ATOMIC_RELAXED))
		return;
	char ffn[48] = "";
	pthread_mutex_lock(&native_drawlog_lock);
	const struct native_drawlog_name *name = native_drawlog_slot(render, false);
	if (name != NULL)
		memcpy(ffn, name->ffn, sizeof(ffn));
	pthread_mutex_unlock(&native_drawlog_lock);
	ffn[sizeof(ffn) - 1] = 0;
	if (strncmp(ffn, "variable_blur_frag", 18) != 0)
		return;
	id rt = ncolors ? colors[0] : nil;
	id src = ntextures > 3 ? textures[3] : nil, mask = ntextures > 4 ? textures[4] : nil;
	if (rt == nil || src == nil || mask == nil || [rt width] < 100 || [rt height] < 100 || nvb < 4 ||
	    vbufs[1] == nil || vbufs[2] == nil || vbufs[3] == nil)
		return;
	if (__atomic_exchange_n(&done, 1, __ATOMIC_RELAXED))
		return;
	int fd = open("/var/local/vblur-capture.bin", O_WRONLY | O_TRUNC);
	if (fd < 0) {
		fprintf(stderr, "SweetNativeMetal: VBCAP cannot open /var/local/vblur-capture.bin: %d\\n", errno);
		return;
	}
	size_t total = 0;
	bool ok = true;
#define VB_PUT(ptr, len) do { if (ok && (len) && write(fd, (ptr), (len)) != (ssize_t)(len)) ok = false; total += (len); } while (0)
#define VB_U32(v) do { uint32_t vb_u = (uint32_t)(v); VB_PUT(&vb_u, 4); } while (0)
	VB_PUT("VBCAP1\0\0", 8);
	VB_U32([rt width]); VB_U32([rt height]); VB_U32([rt pixelFormat]);
	const unsigned isize = index_type == 1 ? 4 : 2;
	VB_U32(primitive); VB_U32(vstart); VB_U32(vcount); VB_U32((uint32_t)base_vertex);
	VB_U32(index_buffer != nil ? index_type : 0xffffffffu);
	unsigned max_index = vstart + vcount;
	if (index_buffer != nil) {
		const uint8_t *ib = (const uint8_t *)[index_buffer contents] + index_offset;
		VB_U32(vcount);
		VB_PUT(ib, (size_t)vcount * isize);
		max_index = 0;
		for (unsigned k = 0; k < vcount; k++) {
			unsigned v = isize == 4 ? ((const uint32_t *)ib)[k] : ((const uint16_t *)ib)[k];
			if (v + 1 > max_index)
				max_index = v + 1;
		}
		max_index += (unsigned)(base_vertex > 0 ? base_vertex : 0);
	} else {
		VB_U32(0);
	}
	const unsigned vb_index[3] = { 1, 2, 3 };
	const size_t vb_len[3] = { (size_t)max_index * 48, 64, 32 };
	for (unsigned i = 0; i < 3; i++) {
		id b = vbufs[vb_index[i]];
		const size_t blen = (size_t)[b length], off = voffs[vb_index[i]];
		const size_t len = off < blen ? (vb_len[i] < blen - off ? vb_len[i] : blen - off) : 0;
		VB_U32(vb_index[i]); VB_U32(len);
		VB_PUT((const uint8_t *)[b contents] + off, len);
	}
	const unsigned fb_index[3] = { 1, 5, 6 };
	for (unsigned i = 0; i < 3; i++) {
		const unsigned k = fb_index[i];
		id b = k < nfb ? fbufs[k] : nil;
		size_t len = 0;
		if (b != nil) {
			const size_t blen = (size_t)[b length], off = foffs[k];
			len = off < blen ? (blen - off < 64 ? blen - off : 64) : 0;
		}
		VB_U32(k); VB_U32(len);
		if (len)
			VB_PUT((const uint8_t *)[b contents] + foffs[k], len);
	}
	id tex[2] = { src, mask };
	for (unsigned i = 0; i < 2; i++) {
		id t = tex[i];
		unsigned levels = (unsigned)[t mipmapLevelCount];
		levels = levels == 0 ? 1 : levels > 12 ? 12 : levels;
		VB_U32(i == 0 ? 3 : 4); VB_U32([t width]); VB_U32([t height]); VB_U32([t pixelFormat]); VB_U32(levels);
		for (unsigned l = 0; l < levels && ok; l++) {
			unsigned w = (unsigned)[t width] >> l, h = (unsigned)[t height] >> l;
			w = w ? w : 1;
			h = h ? h : 1;
			uint8_t *px = malloc((size_t)w * h * 4);
			if (px == NULL) {
				ok = false;
				break;
			}
			[t getBytes:px bytesPerRow:w * 4 fromRegion:MTLRegionMake2D(0, 0, w, h) mipmapLevel:l];
			VB_PUT(px, (size_t)w * h * 4);
			free(px);
		}
	}
#undef VB_U32
#undef VB_PUT
	fsync(fd);
	close(fd);
	fprintf(stderr, "SweetNativeMetal: VBCAP %s: %s rt %ux%u, %zu bytes, %s\\n", ok ? "written" : "FAILED", ffn,
	        (unsigned)[rt width], (unsigned)[rt height], total, ok ? "ok" : "short write");
}

static void
native_xrg_clear(void)
{
	void rwa_texture_mark_opaque(struct rwa_texture *);
	void rwa_render_straight_alpha_next(bool);
	rwa_texture_mark_opaque(NULL);
	rwa_render_straight_alpha_next(false);
}

/* Optional A/B experiment for the 23G90 image-upload site above. */
@interface NSObject (SweetNativeWallUpload)
- (BOOL)nativeQuartzCoreWallpaperUpload;
@end

static bool
native_wall_skip_uploaded_overlay(const void *commands, const void *render,
                                  id const *colors, unsigned ncolors,
                                  id const *textures, unsigned ntextures)
{
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-wallpaper-single-layer-test", F_OK) == 0;
	});
	if (!enabled)
		return false;

	static _Thread_local const void *previous_commands;
	static _Thread_local uintptr_t previous_target;
	static _Thread_local uint32_t previous_surface;
	const void *old_commands = previous_commands;
	const uintptr_t old_target = previous_target;
	const uint32_t old_surface = previous_surface;
	previous_surface = 0;

	id source = ntextures > 3 ? textures[3] : nil;
	id target = ncolors ? colors[0] : nil;
	if (source == nil || target == nil || [source width] != 828 ||
	    [source height] != 1792 || [target width] != 828 || [target height] != 1792)
		return false;

	pthread_mutex_lock(&native_drawlog_lock);
	const struct native_drawlog_name *name = native_drawlog_slot(render, false);
	const bool source_over = name != NULL &&
		!strcmp(name->label, "com.apple.coreanimation.PBGRABsovXm_TimgA2Xhf_Isrc");
	pthread_mutex_unlock(&native_drawlog_lock);
	if (!source_over)
		return false;

	void *surface = [source respondsToSelector:@selector(iosurface)] ?
	                (void *)[source iosurface] : NULL;
	previous_commands = commands;
	previous_target = (uintptr_t)target;
	previous_surface = rwd_surface_id(surface);
	if (previous_surface != 0 || old_surface == 0 || old_commands != commands ||
	    old_target != (uintptr_t)target ||
	    ![source respondsToSelector:@selector(nativeQuartzCoreWallpaperUpload)] ||
	    ![source nativeQuartzCoreWallpaperUpload])
		return false;

	static unsigned skipped;
	if (__atomic_fetch_add(&skipped, 1, __ATOMIC_RELAXED) < 8)
		fprintf(stderr, "SweetNativeMetal: skipped uploaded wallpaper test layer after IOSurface %u\\n",
		        old_surface);
	return true;
}

static void
native_drawlog_draw(unsigned seq,'''),
     ('static void\nnative_drawlog_draw(unsigned seq,',
      'static void native_drawlog_texstat(unsigned seq, id t);\n'
      'static void native_wall_regionstat(unsigned seq, const char *label, id t, unsigned surface);\n\n'
      'static void\nnative_drawlog_draw(unsigned seq,'),
     # TEXSTAT: for a logged glass_background draw, the blur texture it samples (slot 3,
     # source_texture), read back level by level: mean BGRA and the share of fully transparent
     # texels. Tells a broken blur chain (black/clear source) from a broken glass output.
     ('''/* One attribute of one vertex, decoded by MTLVertexFormat. */
''',
      '''static void
native_drawlog_texstat(unsigned seq, id t)
{
	if (t == nil || [t sampleCount] > 1)
		return;
	const unsigned fmt = (unsigned)[t pixelFormat];
	if (fmt != 80 && fmt != 81 && fmt != 70 && fmt != 71) {
		fprintf(stderr, "SweetNativeMetal: TEXSTAT %u format %u not read\\n", seq, fmt);
		return;
	}
	unsigned levels = (unsigned)[t mipmapLevelCount];
	levels = levels == 0 ? 1 : levels > 10 ? 10 : levels;
	for (unsigned l = 0; l < levels; l++) {
		unsigned w = (unsigned)[t width] >> l, h = (unsigned)[t height] >> l;
		w = w ? w : 1;
		h = h ? h : 1;
		const size_t n = (size_t)w * h;
		uint8_t *px = malloc(n * 4);
		if (px == NULL)
			return;
		memset(px, 0xee, n * 4);
		[t getBytes:px bytesPerRow:w * 4 fromRegion:MTLRegionMake2D(0, 0, w, h) mipmapLevel:l];
		uint64_t s[4] = { 0 };
		size_t clear = 0;
		for (size_t i = 0; i < n; i++) {
			for (unsigned k = 0; k < 4; k++)
				s[k] += px[i * 4 + k];
			clear += px[i * 4 + 3] == 0;
		}
		fprintf(stderr, "SweetNativeMetal: TEXSTAT %u L%u %ux%u mean %u,%u,%u,%u clear %u%%\\n", seq, l, w, h,
		        (unsigned)(s[0] / n), (unsigned)(s[1] / n), (unsigned)(s[2] / n), (unsigned)(s[3] / n),
		        (unsigned)(clear * 100 / n));
		free(px);
	}
}

/* WALLREGION (opt-in, /var/local/sweet-native-wall-regions, backboardd only): the full-size
 * wallpaper source the compositor is about to sample, read back as a 3x4 grid of mean BGRA
 * and share of alpha-0 texels per cell. Compared with a USB screenshot of the same frame it
 * tells a wash already in the poster's surface from one added by compositing. At most one
 * readback every 5 s and 40 in total: unbounded backboardd readbacks exhausted GPU
 * allocations once (2026-11-22). */
static void
native_wall_regionstat(unsigned seq, const char *label, id t, unsigned surface)
{
	static dispatch_once_t once;
	static bool enabled;
	dispatch_once(&once, ^{
		const char *process = getprogname();
		enabled = process != NULL && !strcmp(process, "backboardd") &&
		          access("/var/local/sweet-native-wall-regions", F_OK) == 0;
		if (enabled)
			fprintf(stderr, "SweetNativeMetal: WALLREGION enabled (3x4 grid, 5 s, 40 max)\\n");
	});
	if (!enabled || t == nil || [t sampleCount] > 1)
		return;
	const unsigned fmt = (unsigned)[t pixelFormat];
	if (fmt != 80 && fmt != 81)
		return;
	static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
	static uint64_t next_ms;
	static unsigned told;
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	const uint64_t ms = (uint64_t)now.tv_sec * 1000 + (uint64_t)now.tv_nsec / 1000000;
	pthread_mutex_lock(&lock);
	const bool go = told < 40 && ms >= next_ms;
	if (go) {
		told++;
		next_ms = ms + 5000;
	}
	pthread_mutex_unlock(&lock);
	if (!go)
		return;
	const unsigned w = (unsigned)[t width], h = (unsigned)[t height];
	uint8_t *px = malloc((size_t)w * h * 4);
	if (px == NULL)
		return;
	memset(px, 0xee, (size_t)w * h * 4);
	[t getBytes:px bytesPerRow:w * 4 fromRegion:MTLRegionMake2D(0, 0, w, h) mipmapLevel:0];
	char line[1024];
	int at = snprintf(line, sizeof(line), "SweetNativeMetal: WALLREGION %u %s IOSurface %u fmt %u %ux%u", seq,
	                  label, surface, fmt, w, h);
	for (unsigned gy = 0; gy < 4; gy++) {
		for (unsigned gx = 0; gx < 3; gx++) {
			const unsigned x0 = w * gx / 3, x1 = w * (gx + 1) / 3;
			const unsigned y0 = h * gy / 4, y1 = h * (gy + 1) / 4;
			uint64_t sum[4] = { 0 };
			size_t clear = 0, n = 0;
			for (unsigned y = y0; y < y1; y += 2) {
				const uint8_t *row = px + (size_t)y * w * 4;
				for (unsigned x = x0; x < x1; x += 2, n++) {
					for (unsigned k = 0; k < 4; k++)
						sum[k] += row[x * 4 + k];
					clear += row[x * 4 + 3] == 0;
				}
			}
			n = n ? n : 1;
			if (at > 0 && (size_t)at < sizeof(line))
				at += snprintf(line + at, sizeof(line) - at, " r%uc%u=%u,%u,%u,%u/%u%%", gy, gx,
				               (unsigned)(sum[0] / n), (unsigned)(sum[1] / n), (unsigned)(sum[2] / n),
				               (unsigned)(sum[3] / n), (unsigned)(clear * 100 / n));
		}
	}
	fprintf(stderr, "%s\\n", line);
	free(px);
}

/* One attribute of one vertex, decoded by MTLVertexFormat. */
'''),
     ('''	char rt[160] = "", ds[80] = "-", tx[320] = "";
''',
      '''	static dispatch_once_t metadata_once;
	static bool metadata_only;
	dispatch_once(&metadata_once, ^{
		metadata_only = access("/var/local/sweet-native-drawlog-metadata-only", F_OK) == 0;
	});
	if (metadata_only) {
		id source = ntextures > 3 ? textures[3] : nil;
		id target = ncolors ? colors[0] : nil;
		if (source != nil && target != nil && [source width] == [target width] &&
		    [source height] == [target height] && [source width] >= 600 &&
		    [source height] >= 1200 &&
		    (!strcmp(nm.label, "com.apple.coreanimation.PBGRABsovXm_TimgA2Xhf_Isrc") ||
		     !strcmp(nm.label, "com.apple.coreanimation.PBGRAXm_TimgA2Xhf_Ixrg"))) {
			void *surface = [source respondsToSelector:@selector(iosurface)] ?
			                (void *)[source iosurface] : NULL;
			id parent = [source respondsToSelector:@selector(parentTexture)] ?
			            [source parentTexture] : nil;
			fprintf(stderr, "SweetNativeMetal: WALLDRAW %u %s src %p parent %p IOSurface %u usage 0x%lx rt %p\\n",
			        seq, nm.label, (void *)source, (void *)parent, rwd_surface_id(surface),
			        (unsigned long)[source usage], (void *)target);
			native_wall_regionstat(seq, nm.label, source, rwd_surface_id(surface));
		}
		/* Then the DRAW line like the full log, without its GPU readbacks (below). */
	}
	char rt[160] = "", ds[80] = "-", tx[320] = "";
'''),
     ('''	fprintf(stderr, "SweetNativeMetal: DRAW %u %s %s|%s prim %u start %u n %u idx %s@%zu inst %u rt %s ds %s tex %s\\n",
	        seq, nm.label, nm.vfn, nm.ffn, prim, start, count,
	        indexed ? (index_type ? "u32" : "u16") : "-", index_offset, instances, rt, ds,
	        tx[0] ? tx : "-");
}''',
      '''	fprintf(stderr, "SweetNativeMetal: DRAW %u %s %s|%s prim %u start %u n %u idx %s@%zu inst %u rt %s ds %s tex %s\\n",
	        seq, nm.label, nm.vfn, nm.ffn, prim, start, count,
	        indexed ? (index_type ? "u32" : "u16") : "-", index_offset, instances, rt, ds,
	        tx[0] ? tx : "-");
	if (metadata_only)
		;   /* no readbacks: they exhausted GPU allocations in backboardd once */
	else if (!strncmp(nm.ffn, "glass_background", 16) && ntextures > 3)
		native_drawlog_texstat(seq, textures[3]);
	/* Mercury's glass arc samples its blur pyramid (texture 7, blurredBackground) at a
	 * run-time LOD: every level, to tell a stale or flat pyramid from a wrong arc. */
	else if (!strcmp(nm.ffn, "space::rasterizeArcFragment") && ntextures > 7 && textures[7] != nil) {
		static unsigned arc_told;
		if (arc_told++ < 6)
			native_drawlog_texstat(seq, textures[7]);
	}
	/* A full-screen image layer (the wallpaper a poster extension rendered into its own
	 * IOSurface): read what the compositor is about to sample, so a black wallpaper can be
	 * told apart from one that is never composited. */
	else if (ntextures > 3 && textures[3] != nil && [textures[3] width] >= 600 &&
	         [textures[3] height] >= 1200) {
		static unsigned big_told;
		if (big_told++ < 24) {
			id t = textures[3];
			void *surf = [t respondsToSelector:@selector(iosurface)] ? (void *)[t iosurface] : NULL;
			fprintf(stderr, "SweetNativeMetal: TEXSTAT %u full-screen layer %s tex %p surface %p\\n",
			        seq, nm.label, t, surf);
			native_drawlog_texstat(seq, t);
		}
	}
	/* what a full-screen target held before this draw: the previous frame's result, so a
	 * wallpaper that renders black can be told from one that renders and is lost later */
	if (!metadata_only && ncolors > 0 && colors[0] != nil && [colors[0] sampleCount] == 1 &&
	    [colors[0] width] >= 600 && [colors[0] height] >= 1200) {
		static unsigned rt_told;
		if (rt_told++ < 24) {
			fprintf(stderr, "SweetNativeMetal: TEXSTAT %u full-screen target %s format %u\\n", seq,
			        nm.label, (unsigned)[colors[0] pixelFormat]);
			native_drawlog_texstat(seq, colors[0]);
		}
	}
}'''),
     # Periodic arming: the touch-a-file trigger needs a file to change AFTER the process
     # started, which only a delayed package could do, and a delayed package corrupted the
     # catalog once. /var/local/sweet-native-drawlog-every ("SECONDS DRAWS PROCESS", read once,
     # installed at mount like any package) arms the log in that one process every SECONDS.
     ('''\tif (!remaining)
\t\treturn 0;
\tremaining--;''',
      '''\t{
\t\tstatic bool every_read;
\t\tstatic unsigned every_s, every_n;
\t\tstatic uint64_t every_next;
\t\tif (!every_read) {
\t\t\tevery_read = true;
\t\t\tchar name[64] = "";
\t\t\tFILE *f = fopen("/var/local/sweet-native-drawlog-every", "r");
\t\t\tif (f) {
\t\t\t\tif (fscanf(f, "%u %u %63s", &every_s, &every_n, name) != 3 ||
\t\t\t\t    strcmp(name, getprogname()) != 0)
\t\t\t\t\tevery_s = 0;
\t\t\t\tfclose(f);
\t\t\t}
\t\t\tif (every_s) {
\t\t\t\tevery_n = every_n ? (every_n > 20000 ? 20000 : every_n) : 1500;
\t\t\t\tevery_next = ms;   /* the first draw arms: a process that draws in one burst is still seen */
\t\t\t\tfprintf(stderr, "SweetNativeMetal: DRAWLOG every %u s, %u draws\\n", every_s, every_n);
\t\t\t}
\t\t}
\t\tif (every_s && ms >= every_next) {
\t\t\tevery_next = ms + (uint64_t)every_s * 1000;
\t\t\tif (!remaining) {
\t\t\t\tremaining = every_n;
\t\t\t\tnative_drawlog_detail_on = false;
\t\t\t\tfprintf(stderr, "SweetNativeMetal: DRAWLOG armed for %u draws (every %u s)\\n",
\t\t\t\t        every_n, every_s);
\t\t\t}
\t\t}
\t}
\tif (!remaining)
\t\treturn 0;
\tremaining--;'''),
     ('/* One attribute of one vertex, decoded by MTLVertexFormat. */\n',
      '''static void
native_glassstat(const void *render)
{
\tstatic pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
\tstatic uint64_t window_ms;
\tstatic unsigned draws, glass_bg, glass_fg, blur;
\tstatic const void *last_render;
\tstatic int last_cat;
\tstruct timespec now;
\tclock_gettime(CLOCK_MONOTONIC, &now);
\tconst uint64_t ms = (uint64_t)now.tv_sec * 1000 + (uint64_t)now.tv_nsec / 1000000;
\tint cat = 0;
\tbool known = false;
\tpthread_mutex_lock(&lock);
\tif (render == last_render) {
\t\tcat = last_cat;
\t\tknown = true;
\t}
\tpthread_mutex_unlock(&lock);
\tif (!known) {
\t\tchar f[48] = "";
\t\tpthread_mutex_lock(&native_drawlog_lock);
\t\tstruct native_drawlog_name *e = native_drawlog_slot(render, false);
\t\tif (e)
\t\t\tmemcpy(f, e->ffn, sizeof(f));
\t\tpthread_mutex_unlock(&native_drawlog_lock);
\t\tf[sizeof(f) - 1] = 0;
\t\tcat = !strncmp(f, "glass_background", 16) ? 1 :
\t\t      !strncmp(f, "glass_foreground", 16) ? 2 :
\t\t      (strstr(f, "blur") || strstr(f, "downsample") || strstr(f, "upsample")) ? 3 : 0;
\t}
\tpthread_mutex_lock(&lock);
\tlast_render = render;
\tlast_cat = cat;
\tif (!window_ms)
\t\twindow_ms = ms;
\tif (ms - window_ms >= 1000) {
\t\tif (draws)
\t\t\tfprintf(stderr, "SweetNativeMetal: GLASSSTAT %llu ms: draws %u glass_bg %u "
\t\t\t        "glass_fg %u blur %u\\n", (unsigned long long)(ms - window_ms), draws,
\t\t\t        glass_bg, glass_fg, blur);
\t\twindow_ms = ms;
\t\tdraws = glass_bg = glass_fg = blur = 0;
\t}
\tdraws++;
\tglass_bg += cat == 1;
\tglass_fg += cat == 2;
\tblur += cat == 3;
\tpthread_mutex_unlock(&lock);
}

/* CoreAnimation's luma_boost_lph/lpf (QuartzCore 23G90): out.rgb = d0.rgb +
 * scale * edr * LUT(luma(d0) * inv_edr), an EDR brightness lift drawn over the finished
 * frame with framebuffer fetch. backboardd runs it full-screen on the A71, whose panel has
 * no EDR, and the wallpaper came out about twice as bright (owner, 2026-11-22). The draw
 * only adds light, so leaving it out leaves the frame as composited.
 * /var/local/sweet-mtl-skip-luma-boost present = skip it. */
static bool
native_skip_luma_boost(const void *render)
{
\tstatic int skip = -1;
\tstatic const void *last_render;
\tstatic bool last_is;
\tif (skip < 0) {
\t\tskip = access("/var/local/sweet-mtl-skip-luma-boost", F_OK) == 0;
\t\tfprintf(stderr, "SweetNativeMetal: luma_boost draws %s (/var/local/sweet-mtl-skip-luma-boost)\\n",
\t\t        skip ? "skipped" : "drawn");
\t}
\tif (!skip)
\t\treturn false;
\tif (render == last_render)
\t\treturn last_is;
\tchar f[48] = "";
\tpthread_mutex_lock(&native_drawlog_lock);
\tstruct native_drawlog_name *e = native_drawlog_slot(render, false);
\tif (e)
\t\tmemcpy(f, e->ffn, sizeof(f));
\tpthread_mutex_unlock(&native_drawlog_lock);
\tf[sizeof(f) - 1] = 0;
\tlast_render = render;
\tlast_is = !strncmp(f, "luma_boost_", 11);
\tstatic unsigned told;
\tif (last_is && told++ < 4)
\t\tfprintf(stderr, "SweetNativeMetal: skipped %s draw\\n", f);
\treturn last_is;
}

/* One attribute of one vertex, decoded by MTLVertexFormat. */
'''))

edit('tools/mesa/air/air_pointer_cells.inc',
     ('         case AIR_OP_SELECT: {\n',
      '''         case AIR_OP_EXTRACTELT: {
            if (in->num_operands != 2)
               return false;
            const struct air_type *vector = in->operands[0]->type;
            struct sev value = sev_get(st, in->operands[0]);
            struct sev index = sev_get(st, in->operands[1]);
            if (!vector || vector->kind != AIR_TYPE_VECTOR || !value.ok ||
                !index.ok || index.n > 8 || !n)
               return false;
            uint64_t lane = sev_u(&index);
            if (lane >= vector->count || lane >= value.n / n)
               return false;
            struct sev element = { .ok = true, .n = n };
            memcpy(element.b, value.b + lane * n, n);
            sev_set(st, &in->base, element);
            break;
         }
         case AIR_OP_SELECT: {
'''),
     ('''static bool
sev_fc_value(const struct air_ctx *c, unsigned index, uint64_t *bits)
{
   for (unsigned i = 0; c->options && i < c->options->num_constants; i++)
      if (c->options->constants[i].index == index) {
         *bits = c->options->constants[i].bits;
         return true;
      }
   return false;
}
''',
      '''static const struct air_constant_value *
sev_fc_value(const struct air_ctx *c, unsigned index)
{
   for (unsigned i = 0; c->options && i < c->options->num_constants; i++)
      if (c->options->constants[i].index == index)
         return &c->options->constants[i];
   return NULL;
}
'''),
     ('''      uint64_t bits = 0;
      (void)sev_fc_value(c, pl->binding, &bits);   /* undefined: 0 refines undef */
      if (off + n > 8)
         return false;
      for (unsigned b = 0; b < n; b++)
         out->b[b] = bits >> (8 * (off + b));
''',
      '''      const struct air_constant_value *v = sev_fc_value(c, pl->binding);
      const uint64_t words[2] = { v ? v->bits : 0, v ? v->bits_hi : 0 };
      if (off > sizeof(words) || n > sizeof(words) - off)
         return false;
      for (unsigned b = 0; b < n; b++) {
         const unsigned byte = off + b;
         out->b[b] = words[byte / 8] >> (8 * (byte % 8));
      }
'''),
     ('''               uint64_t off, bits;
''', '               uint64_t off;\n'),
     ('''               sev_set(st, &in->base, sev_of_u(sev_fc_value(c, c->global_plan[g].binding, &bits), 1));
''',
      '''               sev_set(st, &in->base, sev_of_u(sev_fc_value(c, c->global_plan[g].binding) != NULL, 1));
'''),
     ('static bool\nsev_run(struct sev_state *st, const struct air_function *f)\n',
      '''static const struct air_block *switch_known_target(const struct air_inst *, uint64_t, unsigned);

static bool
sev_run(struct sev_state *st, const struct air_function *f)
'''),
     ('            if (!strcmp(name, "air.is_function_constant_defined")) {\n',
      '''            if (!strcmp(name, "air.convert.f.f32.u.i1")) {
               struct sev v = in->num_operands == 2 ? sev_get(st, in->operands[1]) : (struct sev){0};
               if (!v.ok || v.n != 1 || n != 4)
                  return false;
               /* An unsigned boolean becomes IEEE-754 0.0f or 1.0f. */
               sev_set(st, &in->base, sev_of_u((v.b[0] & 1) ? 0x3f800000u : 0, n));
               break;
            }
            if (!strcmp(name, "air.is_function_constant_defined")) {
'''),
     ('         case AIR_OP_RET:\n            return true;\n',
      '''         case AIR_OP_SWITCH: {
            if (!in->num_targets || in->num_targets != in->num_operands)
               return false;
            const struct air_type *type = in->operands[0]->type;
            struct sev selector = sev_get(st, in->operands[0]);
            if (!type || type->kind != AIR_TYPE_INT || !selector.ok || !type->bits ||
                type->bits > 64 || selector.n != (type->bits + 7) / 8)
               return false;
            next = switch_known_target(in, sev_u(&selector), type->bits);
            if (!next)
               return false;
            break;
         }
         case AIR_OP_RET:
            return true;
'''))

edit('tools/mesa/air/sweet_native_ext.h',
     ('struct rwa_constant { unsigned index; const char *name; uint64_t bits; unsigned bytes; };\n',
      'struct rwa_constant { unsigned index; const char *name; uint64_t bits; unsigned bytes; uint64_t bits_hi; };\n'))

edit('tools/mesa/air/sweet_native_ext.c',
     ('''   for(unsigned i=0;i<count;i++) if(!values[i].bytes || values[i].bytes>8) {
      say(why,n,"interface: function constant exceeds AIR's 64-bit value representation");return -1;
''',
      '''   for(unsigned i=0;i<count;i++) if(!values[i].bytes || values[i].bytes>16) {
      say(why,n,"interface: function constant exceeds AIR's 128-bit value representation");return -1;
'''),
     ('''            (*out)[count]=declared[i];(*out)[count++].bits=v->bits;break;
''',
      '''            (*out)[count] = declared[i];
            (*out)[count].bits = v->bits;
            (*out)[count++].bits_hi = v->bits_hi;
            break;
'''))

edit('userland/src/SweetNativeLibrary.inc',
     ('    case 4:case 30:case 34:return 8;\n',
      '    case 4:case 30:case 34:return 8;\n'
      '    case 5:case 31:case 35:return 12;   /* float3, int3, uint3 */\n'
      '    case 6:case 32:case 36:return 16;   /* float4, int4, uint4 */\n'),
     ('''        BOOL valid=YES;
        for(unsigned group=0;group<2;group++)for(id value in (group?named:indexed)) {
            if(!native_method_abi(value,@selector(dataType),"Q16@0:8") ||
               !native_method_abi(value,@selector(data),"^v16@0:8") ||
               !native_method_abi(value,group?@selector(name):@selector(index),group?"@16@0:8":"Q16@0:8")) {valid=NO;break;}
            unsigned n=native_constant_bytes([value dataType]);
            if(!n || ![value data]){valid=NO;break;}
            NSData *packed=[NSData dataWithBytes:[value data] length:n];
            id key=group?[value name]:@([value index]);
            if(!key){valid=NO;break;}
            [constants addObject:@{@"key":key,@"bytes":packed}];
        }
        [indexed release];[named release];[snapshot release];
        if(!valid){if(error)*error=native_error("unsupported constant type or value ABI (AIR limit: 64 bits)");return nil;}
''',
      '''        char failure[160] = {0};
        for (unsigned group = 0; group < 2 && !failure[0]; group++) {
            for (id value in (group ? named : indexed)) {
                BOOL type_ok = native_method_abi(value, @selector(dataType), "Q16@0:8");
                BOOL data_ok = native_method_abi(value, @selector(data), "^v16@0:8");
                BOOL key_ok = native_method_abi(value, group ? @selector(name) : @selector(index),
                                                group ? "@16@0:8" : "Q16@0:8");
                if (!type_ok || !data_ok || !key_ok) {
                    snprintf(failure, sizeof(failure), "constant method ABI mismatch (type=%d data=%d key=%d)",
                             type_ok, data_ok, key_ok);
                    break;
                }
                NSUInteger type = [value dataType];
                unsigned n = native_constant_bytes(type);
                if (!n) {
                    snprintf(failure, sizeof(failure), "unsupported function constant Metal type %lu",
                             (unsigned long)type);
                    break;
                }
                const void *data = [value data];
                id key = group ? [value name] : @([value index]);
                if (!data || !key) {
                    snprintf(failure, sizeof(failure), "function constant is missing its key or data");
                    break;
                }
                [constants addObject:@{@"key":key, @"bytes":[NSData dataWithBytes:data length:n]}];
            }
        }
        [indexed release];[named release];[snapshot release];
        if (failure[0]) { if (error) *error = native_error(failure); return nil; }
'''),
     ('''        packed[i].bytes=(unsigned)[bytes length];memcpy(&packed[i].bits,[bytes bytes],[bytes length]);
''',
      '''        const uint8_t *data = [bytes bytes];
        packed[i].bytes = (unsigned)[bytes length];
        size_t low = MIN((size_t)packed[i].bytes, sizeof(packed[i].bits));
        memcpy(&packed[i].bits, data, low);
        if (packed[i].bytes > low)
            memcpy(&packed[i].bits_hi, data + low, packed[i].bytes - low);
'''))

# Mercury's wallpaper drawable: a BGRA IOSurface (207x448, pitch 832) viewed as
# MTLPixelFormatR32Uint ("no drawable ... Metal format 53 ... is not a supported linear
# import"), so Mercury never drew and the wallpaper stayed black. A 32-bit single-channel
# format over a 4-byte-per-pixel surface is the same memory read another way.
edit('userland/src/redwooddrawable.m',
     ("    case 115:fourcc='RGhA';bpp=8;break;\n",
      "    case 94:fourcc='l10r';bpp=4;break;   /* little-endian ARGB2101010 */\n"
      "    case 115:fourcc='RGhA';bpp=8;break;\n"
      "    case 53:case 54:case 55:   /* R32Uint/Sint/Float over a 4-byte surface */\n"
      "        fourcc=(surface_format=='RGBA'||surface_format=='BGRA')?surface_format:'BGRA';bpp=4;break;\n"),
     # Straight-alpha surfaces (A71 2026-11-23): Mercury writes non-premultiplied rgb with an occlusion
     # mask in alpha into every surface it renders. Tag those surfaces (an IOSurface value, visible to
     # backboardd), so backboardd blends any image pass of them as straight alpha from the first frame,
     # including transitions where a surface is shown before it was ever drawn opaque.
     ("uint32_t rwd_surface_id(void *surface) {return surface?IOSurfaceGetID((IOSurfaceRef)surface):0;}\n",
      "uint32_t rwd_surface_id(void *surface) {return surface?IOSurfaceGetID((IOSurfaceRef)surface):0;}\n"
      "int rwd_surface_straight_alpha(void *surface);\n"
      "int rwd_surface_straight_alpha(void *surface)\n"
      "{\n"
      "    if(!surface)return 0;\n"
      "    CFTypeRef v=IOSurfaceCopyValue((IOSurfaceRef)surface,CFSTR(\"SweetA71StraightAlpha\"));\n"
      "    const int yes=v!=NULL && CFEqual(v,kCFBooleanTrue);\n"
      "    if(v)CFRelease(v);\n"
      "    return yes;\n"
      "}\n"),
     ("    if(!device || !s || !want)REFUSE(\"IOSurface import requires a device, surface and descriptor\");\n",
      "    if(!device || !s || !want)REFUSE(\"IOSurface import requires a device, surface and descriptor\");\n"
      "    if((want->usage&4u) && getprogname() && !strcmp(getprogname(),\"MercuryPosterExtension\") &&\n"
      "       access(\"/var/local/sweet-native-wallpaper-depth\",F_OK)==0) {\n"
      "        IOSurfaceSetValue(s,CFSTR(\"SweetA71StraightAlpha\"),kCFBooleanTrue);\n"
      "        static unsigned told_straight;\n"
      "        if(told_straight++<8)fprintf(stderr,\"SweetNativeMetal: XRGALPHA tagged IOSurface %u (straight alpha)\\n\",IOSurfaceGetID(s));\n"
      "    }\n"))

Path('userspace/native-metal/ios26-image-write-levels.patch').write_text(''.join(changes), encoding='utf-8',
                                                                         newline='\n')
