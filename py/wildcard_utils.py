# wildcard_utils.py
import os
import re
import functools



# ---------- helpers for normalizing contexts ----------
def _ensure_bucket_dict(bucket_like):
    """
    Convert incoming bucket to canonical dict(origin->value).
    Accepts:
        - dict: assumed origin->value mapping -> returned as-is (copy)
        - list/tuple: converted to { "__combined_0": v0, "__combined_1": v1, ... }
        - single value: converted to { "__combined_0": value }
    """
    if bucket_like is None:
        return {}
    if isinstance(bucket_like, dict):
        # copy and stringify values
        out = {}
        for k, v in bucket_like.items():
            out[str(k)] = str(v)
        return out
    if isinstance(bucket_like, (list, tuple, set)):
        out = {}
        i = 0
        for v in bucket_like:
            out[f"__combined_{i}"] = str(v)
            i += 1
        return out
    # single scalar
    return {"__combined_0": str(bucket_like)}

def _normalize_input_context(ctx):
    """
    Convert arbitrary incoming context into dict[var_name] -> dict[origin->value].
    """
    if not ctx:
        return {}
    normalized = {}
    for var, bucket in ctx.items():
        normalized[var] = _ensure_bucket_dict(bucket)
    return normalized

def _snapshot_context(context: dict) -> dict:
    """
    Creates a snapshot of the current keys in the context.
    Used in conjunction with `_apply_context_override` to support "override" logic.
    """
    snapshot = {}
    for k, v in context.items():
        if isinstance(v, dict):
            snapshot[k] = list(v.keys())
    return snapshot

def _apply_context_override(context: dict, snapshot: dict) -> None:
    """
    Compares the current context against a snapshot. If a variable had new origins added
    since the snapshot, the old origins are deleted, effectively "overriding" the old values.
    Modifies the context in-place.
    """
    for k, old_keys in snapshot.items():
        if k in context and isinstance(context[k], dict):
            current_keys = list(context[k].keys())
            new_keys = [key for key in current_keys if key not in old_keys]
            if new_keys:
                for old_k in old_keys:
                    del context[k][old_k]


def _default_package_root():
    # package root is one directory above the module file
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

@functools.lru_cache(maxsize=4)
def build_category_options(base_dir: str | None = None):
    """
    Discover folders beginning with 'wildcards' inside 'base_dir' (defaults to package root).
    Returns: (labels_list, label_to_folder_map, tooltip_str)

    - 'wildcards' -> label 'Default'
    - 'wildcards_foo' -> label 'FOO' (suffix uppercased)
    - Always ensures at least 'wildcards' exists (fallback)
    """
    if base_dir is None:
        base_dir = _default_package_root()

    folder_names = []
    try:
        for name in os.listdir(base_dir):
            path = os.path.join(base_dir, name)
            if os.path.isdir(path) and name.startswith("wildcard"):
                folder_names.append(name)
    except Exception:
        folder_names = []

    # Ensure 'wildcards' fallback exists in the list (so user always has at least Default)
    if "wildcards" not in folder_names:
        # prefer to put real existing 'wildcards' first if present else ensure at least label
        folder_names.insert(0, "wildcards")

    label_list = []
    label_to_folder = {}
    for fname in folder_names:
        label = fname
        label_list.append(label)
        # map label to absolute folder path under base_dir
        label_to_folder[label] = os.path.join(base_dir, fname)

    tooltip = (
        "Select which wildcards folder to use. Create alternate folders named "
        "'wildcards_*' (eg. 'wildcards_fresh') inside the package root.\n\n"
        "defaults to the global '/wildcards/ if a file is missing'"
    )

    return label_list, label_to_folder, tooltip

def clear_category_cache():
    """
    Clear the cached results (useful if you add/remove wildcard folders at runtime
    and need the dropdowns to refresh).
    """
    build_category_options.cache_clear()

def _split_case_result(choice: str) -> tuple[str, str | None]:
    paren_depth = 0
    brace_depth = 0
    bracket_depth = 0
    for i, c in enumerate(choice):
        if c == '(': paren_depth += 1
        elif c == ')': paren_depth -= 1
        elif c == '{': brace_depth += 1
        elif c == '}': brace_depth -= 1
        elif c == '[': bracket_depth += 1
        elif c == ']': bracket_depth -= 1
        elif c == ':' and paren_depth == 0 and brace_depth == 0 and bracket_depth == 0:
            return choice[:i], choice[i+1:]
    return choice, None

def is_conditional_bracket_content(first_choice: str) -> bool:
    """
    Determines if a raw bracket segment is a conditional (switch).
    """
    first_choice = first_choice.strip()
    return bool(re.match(r"^switch\s*\((.*?)\)$", first_choice, re.DOTALL))

def handle_conditional_branches(raw_choices: list[str], resolved_vars: dict, resolve_wildcards_func, kwargs: dict) -> str | None:
    """
    Checks if the raw choices represent a conditional branch (switch).
    If they do, it parses, evaluates the condition, and returns the appropriate 
    unresolved branch string for lazy evaluation. 
    Returns None if it is not a conditional statement.
    """
    if not raw_choices:
        return None
        
    first_choice = raw_choices[0].strip()

    # --- SWITCH STATEMENT ---
    m_switch = re.match(r"^switch\s*\((.*?)\)$", first_choice, re.DOTALL)
    if m_switch:
        switch_var = m_switch.group(1).strip()
        
        # evaluate dynamic variables in condition
        switch_var = resolve_wildcards_func(
            switch_var, **kwargs
        ).strip()

        var_values = []
        if resolved_vars and switch_var in resolved_vars:
            var_values = list(resolved_vars[switch_var].values())

        default_res = ""
        has_default = False

        for choice in raw_choices[1:]:
            case_val, res_val = _split_case_result(choice)
            if res_val is not None:
                case_val = case_val.strip()
                
                if case_val == "default":
                    default_res = res_val
                    has_default = True
                elif case_val in var_values:
                    return res_val
                    
        if has_default:
            return default_res
        return ""
        
    return None
