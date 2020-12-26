#!/usr/bin/env python3
import cxxfilt
import zlib
from typing import List, Dict, Iterable, Optional

from pathlib import Path
import textwrap
from util import ai_common


def get_member_name(entry) -> str:
    type_ = entry["type"]
    if type_ == "dynamic_param":
        return f'm{entry["param_name"]}_d'
    elif type_ == "dynamic2_param":
        return f'm{entry["param_name"]}_d'
    elif type_ == "static_param":
        return f'm{entry["param_name"]}_s'
    elif type_ == "map_unit_param":
        return f'm{entry["param_name"]}_m'
    elif type_ == "aitree_variable":
        return f'm{entry["param_name"]}_a'
    else:
        assert False


def generate_action_loadparam_body(info: list) -> str:
    out = []
    for entry in info:
        type_ = entry["type"]
        if type_ == "dynamic_param":
            if entry["param_name"]:
                out.append(f'getDynamicParam(&{get_member_name(entry)}, "{entry["param_name"]}");')
        elif type_ == "dynamic2_param":
            if entry["param_name"]:
                out.append(f'getDynamicParam2(&{get_member_name(entry)}, "{entry["param_name"]}");')
        elif type_ == "static_param":
            if entry["param_name"]:
                out.append(f'getStaticParam(&{get_member_name(entry)}, "{entry["param_name"]}");')
        elif type_ == "map_unit_param":
            if entry["param_name"]:
                out.append(f'getMapUnitParam(&{get_member_name(entry)}, "{entry["param_name"]}");')
        elif type_ == "aitree_variable":
            if entry["param_name"]:
                out.append(f'getAITreeVariable(&{get_member_name(entry)}, "{entry["param_name"]}");')
        elif type_ == "call":
            fn_name: str = entry["fn"]
            if fn_name.startswith("_ZN") and fn_name.endswith("11loadParams_Ev"):
                parent_class_name = cxxfilt.demangle(fn_name).split("::")[-2]
                out.append(f"{parent_class_name}::loadParams_();")
            else:
                out.append(f"// FIXME: CALL {fn_name} @ {entry['addr']:#x}")
        else:
            raise AssertionError(f"unknown type: {type_}")

    return "\n".join(out)


def generate_action_param_member_vars(parent: str, info: list) -> str:
    out = []

    # Ignore duplicate calls to getXXXXXParam
    params_dict = dict()
    for entry in info:
        offset: Optional[int] = entry.get("param_offset")
        if offset is not None:
            params_dict[offset] = entry
    params = list(params_dict.values())
    params.sort(key=lambda entry: entry["param_offset"])

    if not parent and params:
        first_offset: int = params[0]["param_offset"]
        sizeof_action = 0x20
        diff = first_offset - sizeof_action
        assert diff >= 0
        if diff > 0:
            out.append(f"// FIXME: remove this")
            out.append(f"u8 pad_0x20[{diff:#x}];")

    for entry in params:
        if not entry["param_name"]:
            continue
        out.append(f"// {entry['type']} at offset {entry['param_offset']:#x}")
        out.append(f"{entry['param_type']} {get_member_name(entry)}{{}};")
    return "\n".join(out)


def generate_action(class_dir: Path, name: str, info: list, parent: str) -> None:
    name = name[0].upper() + name[1:]
    if parent:
        parent = parent[0].upper() + parent[1:]

    cpp_class_name = f"{name}"
    header_file_name = f"action{name}.h"

    parent_class_name = parent if parent else 'ksys::act::ai::Action'

    # Header
    out = []
    out.append("#pragma once")
    out.append("")
    if parent:
        out.append(f'#include "Game/AI/Action/action{parent}.h"')
    out.append('#include "KingSystem/ActorSystem/actAiAction.h"')
    out.append("")
    out.append("namespace uking::action {")
    out.append("")
    out.append(f"class {cpp_class_name} : public {parent_class_name} {{")
    out.append(f"    SEAD_RTTI_OVERRIDE({cpp_class_name}, {parent_class_name})")
    out.append("public:")
    out.append(f"    explicit {cpp_class_name}(const InitArg& arg);")
    out.append(f"    ~{cpp_class_name}() override;")
    out.append("")
    out.append("    bool init_(sead::Heap* heap) override;")
    out.append("    void enter_(ksys::act::ai::InlineParamPack* params) override;")
    out.append("    void leave_() override;")
    out.append("    void loadParams_() override;")
    out.append("")
    out.append("protected:")
    out.append("    void calc_() override;")
    out.append("")
    out.append(textwrap.indent(generate_action_param_member_vars(parent, info), " " * 4))
    out.append("};")  # =================================== end of class
    out.append("")
    out.append("}  // namespace uking::action")
    out.append("")
    (class_dir / header_file_name).write_text("\n".join(out))

    # .cpp
    out = []
    out.append(f'#include "Game/AI/Action/{header_file_name}"')
    out.append("")
    out.append("namespace uking::action {")
    out.append("")
    out.append(f"{cpp_class_name}::{cpp_class_name}(const InitArg& arg) : {parent_class_name}(arg) {{}}")
    out.append("")
    out.append(f"{cpp_class_name}::~{cpp_class_name}() = default;")
    out.append("")
    out.append(f"bool {cpp_class_name}::init_(sead::Heap* heap) {{")
    out.append(f"    return {parent_class_name}::init_(heap);")
    out.append(f"}}")
    out.append("")
    out.append(f"void {cpp_class_name}::enter_(ksys::act::ai::InlineParamPack* params) {{")
    out.append(f"    {parent_class_name}::enter_(params);")
    out.append(f"}}")
    out.append("")
    out.append(f"void {cpp_class_name}::leave_() {{")
    out.append(f"    {parent_class_name}::leave_();")
    out.append(f"}}")
    out.append("")
    out.append(f"void {cpp_class_name}::loadParams_() {{")
    out.append(textwrap.indent(generate_action_loadparam_body(info), " " * 4))
    out.append(f"}}")
    out.append("")
    out.append(f"void {cpp_class_name}::calc_() {{")
    out.append(f"    {parent_class_name}::calc_();")
    out.append(f"}}")
    out.append("")
    out.append("}  // namespace uking::action")
    out.append("")
    (class_dir / f"action{name}.cpp").write_text("\n".join(out))


def generate_action_factories(class_dir: Path, actions: Iterable[str]) -> None:
    out = []
    out.append("""\
// DO NOT MAKE MAJOR EDITS. This file is automatically generated.
// For major edits, please edit the generator script (ai_generate_queries.py) instead.
// If edits are made to this file, make sure they are not lost when the generator is re-run.
""")
    out.append('#include "Game/AI/aiActionFactories.h"')
    out.append('#include <array>')
    for name in actions:
        name = name[0].upper() + name[1:]
        out.append(f'#include "Game/AI/Action/action{name}.h"')
    out.append('#include "KingSystem/ActorSystem/actAiAction.h"')
    out.append('')
    out.append('namespace uking {')
    out.append('')
    out.append('using Factory = ksys::act::ai::ActionFactory;')
    out.append('')
    out.append('static Factory sActionFactories[] = {')
    for name in sorted(actions, key=lambda name: zlib.crc32(name.encode())):
        class_name = "action::" + name[0].upper() + name[1:]
        out.append(f'    {{0x{zlib.crc32(name.encode()):08x}, Factory::make<{class_name}>}},')
    out.append('};')
    out.append('')
    out.append('void initActionFactories() {')
    out.append('    ksys::act::ai::Actions::setFactories(std::size(sActionFactories), sActionFactories);')
    out.append('}')
    out.append('')
    out.append('}  // namespace uking')
    (class_dir.parent / f"aiActionFactories.cpp").write_text("\n".join(out))


def main() -> None:
    src_root = Path(__file__).parent.parent
    class_dir = src_root / "src" / "Game" / "AI" / "Action"
    class_dir.mkdir(exist_ok=True)

    action_vtables: Dict[str, List[int]] = ai_common.get_ai_vtables()["Action"]
    action_params = ai_common.get_action_params()
    vtable_names = ai_common.get_action_vtable_names()

    generated = set()
    for vtables in action_vtables.values():
        vtables = list(dict.fromkeys(vtables))
        for i in range(len(vtables)):
            # This skips the first base class.
            if i == 0:
                continue

            vtable_parent = vtables[i - 1]
            vtable = vtables[i]

            # This skips any other base class.
            if vtable in ai_common.BaseClasses:
                continue

            action_name = vtable_names[vtable]
            parent_name = vtable_names[vtable_parent]
            if vtable_parent in ai_common.BaseClasses:
                parent_name = ""

            if vtable not in generated:
                generated.add(vtable)
                generate_action(class_dir, action_name, action_params[action_name], parent_name)

    generate_action_factories(class_dir, action_vtables.keys())


if __name__ == '__main__':
    main()