"""Generate userspace/native-metal/ios26-image-write-levels.patch against the donor tree.

Metal's texture.write(value, coord, lod) may name the mip level at run time (Mercury's
VariableBlurrer::downsample builds its chain that way). A Gallium image view is one level,
so every texture written at a level other than a constant 0 gets up to eight extra image
slots, slot base+k bound to level k of the same texture, and the store picks its slot from
the level. Applies after ios26-mip-views.patch and ios26-blur-attachments.patch.
"""
from pathlib import Path
from difflib import unified_diff

r = Path('research/ios26/native-glass-src/donor')
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
   nir_function *fn = translate_callee(c, f, argv, is_param);
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
            continue; /* a phi in an unreachable block */'''))

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
 * image binding, at most eight and never past the sixteen image slots the runtime has.
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
   unsigned n = next < AIR_IMAGE_SLOTS ? MIN2(8, AIR_IMAGE_SLOTS - next) : 0;
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
   if (v->kind == AIR_VAL_PTR)
      return v->ptr.class == AIR_PTR_NONE ? nir_imm_true(&c->b) : nir_imm_false(&c->b);
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
{'''))

edit('tools/mesa/air/air_metal.c',
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
                        unsigned slice);
int
rwa_texture_resolve(struct rwa_texture *src, struct rwa_texture *dst, unsigned level,
                    unsigned slice)
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
   dst->device->pipe->blit(dst->device->pipe, &b);
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
      'unbind:\n   native_draw_checkpoint(device,&native_phase_at,3);\n   device->hazard_count = 0;\n'))

# newBufferWithBytesNoCopy: Mercury's KTX loader makes its staging buffer this way and the
# driver answered nil ("Failed to create staging buffer"). The GPU cannot map the caller's
# pages here, so the bytes are copied into a buffer of our own, and the caller's
# deallocator runs when that buffer goes away, as Metal promises. A caller that writes the
# pages after this call is not seen; the loader fills them first.
edit('userland/src/redwoodmetal.m',
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
                        unsigned slice);

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
                if (rwa_texture_resolve([src mesaTexture], [dst mesaTexture], lvl, sl) != 0)
                    RW_ONCE("a multisample resolve failed\\n");
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
      '\tnative_glassstat([work->render render]);\n\tconst unsigned dl = native_drawlog_next();\n'))

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
      'static void native_drawlog_texstat(unsigned seq, id t);\n\nstatic void\nnative_drawlog_draw(unsigned seq,'),
     # TEXSTAT: for a logged glass_background draw, the blur texture it samples (slot 3,
     # source_texture), read back level by level: mean BGRA and the share of fully transparent
     # texels. Tells a broken blur chain (black/clear source) from a broken glass output.
     ('''/* One attribute of one vertex, decoded by MTLVertexFormat. */
''',
      '''static void
native_drawlog_texstat(unsigned seq, id t)
{
	if (t == nil)
		return;
	const unsigned fmt = (unsigned)[t pixelFormat];
	if (fmt != 80 && fmt != 81 && fmt != 70 && fmt != 71) {
		fprintf(stderr, "SweetNativeMetal: TEXSTAT %u format %u not read\\n", seq, fmt);
		return;
	}
	unsigned levels = (unsigned)[t mipmapLevelCount];
	levels = levels == 0 ? 1 : levels > 4 ? 4 : levels;
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

/* One attribute of one vertex, decoded by MTLVertexFormat. */
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
	if (!strncmp(nm.ffn, "glass_background", 16) && ntextures > 3)
		native_drawlog_texstat(seq, textures[3]);
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
\t\t\t\tevery_next = ms + (uint64_t)every_s * 1000;
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
      "        fourcc=(surface_format=='RGBA'||surface_format=='BGRA')?surface_format:'BGRA';bpp=4;break;\n"))

Path('userspace/native-metal/ios26-image-write-levels.patch').write_text(''.join(changes), encoding='utf-8',
                                                                         newline='\n')
