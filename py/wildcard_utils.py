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
    """
    Splits a case choice into (label, body) using the FIRST colon found at depth 0.
    
    Key modification for hybrid syntax: 
    - Tracks depth for `()`, `{}`, `[]`, AND `<>`. 
    - Tracking `<>` unconditionally is crucial because if we skipped SD Loras (e.g., `<lora:name:1.0>`), 
      the parser would treat the colons *inside* the Lora as the case label separator, breaking the prompt.
    """
    paren_depth = brace_depth = bracket_depth = angle_depth = 0
    for i, c in enumerate(choice):
        if c == '(': paren_depth += 1
        elif c == ')': paren_depth -= 1
        elif c == '{': brace_depth += 1
        elif c == '}': brace_depth -= 1
        elif c == '[': bracket_depth += 1
        elif c == ']': bracket_depth -= 1
        elif c == '<': angle_depth += 1
        elif c == '>': angle_depth -= 1
        elif c == ':' and paren_depth == 0 and brace_depth == 0 and bracket_depth == 0 and angle_depth == 0:
            return choice[:i], choice[i+1:]
    return choice, None

def is_conditional_bracket_content(first_choice: str) -> bool:
    """
    Determines if a raw bracket segment is a conditional (switch or if).
    """
    first_choice = first_choice.strip()
    return bool(re.match(r"^switch\s*\((.*?)\)$", first_choice, re.DOTALL)) or \
           bool(re.match(r"^if\s*\((.*?)\)$", first_choice, re.DOTALL))

def handle_conditional_branches(raw_choices: list[str], resolved_vars: dict, resolve_wildcards_func, kwargs: dict) -> str | None:
    """
    Checks if the raw choices represent a conditional branch (switch or if).
    If so, it evaluates the condition and returns the chosen unresolved branch string 
    for lazy evaluation by the core engine.
    
    Key modification for hybrid syntax:
    - Employs a helper `_eval_var` to evaluate variables stored lazily in `_resolved_vars` 
      (e.g. `<color={red|blue}>`) so their values can be accurately checked against condition labels.
      
    Returns None if it is not a conditional statement.
    Evaluates {if(...)} and {switch(...)} conditionals locally.
    Returns the resolved string if it was a conditional, otherwise None.
    """
    if not raw_choices:
        return None
        
    first_choice = raw_choices[0].strip()
    
    unres_map = kwargs.get("unres_map", {})
    rw_kwargs_safe = {k: v for k, v in kwargs.items() if k != "unres_map"}

    def _eval_var(v_list):
        for v in v_list:
            evaluated = resolve_wildcards_func(v, **rw_kwargs_safe).strip()
            yield _restore(evaluated)

    def _restore(val: str) -> str:
        for ph, orig in unres_map.items():
            val = val.replace(ph, orig)
        return val

    # --- IF STATEMENT ---
    m_if = re.match(r"^if\s*\((.*?)\)$", first_choice, re.DOTALL)
    if m_if:
        condition_str = m_if.group(1).strip()
        
        # Evaluate dynamic variables in the condition name itself
        condition_str = resolve_wildcards_func(condition_str, **rw_kwargs_safe).strip()
        condition_str = _restore(condition_str)
        
        is_true = False
        
        if "==" in condition_str:
            var_part, val_part = condition_str.split("==", 1)
            var_part = var_part.strip()
            
            var_values = []
            if resolved_vars and var_part in resolved_vars:
                var_values = list(_eval_var(resolved_vars[var_part].values()))
                
            allowed_vals = [v.strip() for v in val_part.split("|")]
            
            # THE UNDEFINED PARADOX (==):
            # If a variable is undefined, it has 0 values. We mathematically treat undefined variables as empty strings "".
            # Therefore, if the user explicitly checks `if(missing==)` (which checks if it equals ""), this will be TRUE.
            # But if they check `if(missing==blue)`, it will be FALSE because "" != "blue".
            if len(var_values) == 0:
                if "" in allowed_vals:
                    is_true = True
            else:
                for v in var_values:
                    if v.strip() in allowed_vals:
                        is_true = True
                        break
        elif "!=" in condition_str:
            var_part, val_part = condition_str.split("!=", 1)
            var_part = var_part.strip()
            
            var_values = []
            if resolved_vars and var_part in resolved_vars:
                var_values = list(_eval_var(resolved_vars[var_part].values()))
                
            allowed_vals = [v.strip() for v in val_part.split("|")]
            
            # THE UNDEFINED PARADOX (!=):
            # If a variable is undefined, we treat it as an empty string "".
            # If the user checks `if(missing!=blue)`, this is logically TRUE because "" is not "blue".
            # However, if they check `if(missing!=)` (not empty), this is FALSE because "" IS "".
            if len(var_values) == 0:
                if "" not in allowed_vals:
                    is_true = True
            else:
                for v in var_values:
                    if v.strip() not in allowed_vals:
                        is_true = True
                        break
        elif condition_str.startswith("empty(") and condition_str.endswith(")"):
            var_part = condition_str[6:-1].strip()
            var_values = []
            if resolved_vars and var_part in resolved_vars:
                var_values = list(_eval_var(resolved_vars[var_part].values()))
            
            # True if undefined OR all values are empty
            if not var_values or all(v.strip() == "" for v in var_values):
                is_true = True
        else:
            var_part = condition_str.strip()
            if resolved_vars and var_part in resolved_vars:
                is_true = len(resolved_vars[var_part]) > 0

        true_res = ""
        default_res = ""
        for choice in raw_choices[1:]:
            case_val, res_val = _split_case_result(choice)
            if res_val is not None and case_val.strip() == "default":
                default_res = res_val
            elif not true_res:
                true_res = choice
                
        if is_true:
            return true_res
        else:
            return default_res

    # --- SWITCH STATEMENT ---
    m_switch = re.match(r"^switch\s*\((.*?)\)$", first_choice, re.DOTALL)
    if m_switch:
        switch_var = m_switch.group(1).strip()
        
        # Evaluate dynamic variables in the condition name itself
        switch_var = resolve_wildcards_func(switch_var, **rw_kwargs_safe).strip()
        switch_var = _restore(switch_var)

        var_values = []
        if resolved_vars and switch_var in resolved_vars:
            var_values = list(_eval_var(resolved_vars[switch_var].values()))

        default_res = ""
        has_default = False
        
        accumulated_cases = []
        default_pending = False

        for choice in raw_choices[1:]:
            case_val, res_val = _split_case_result(choice)
            if res_val is not None:
                case_val = case_val.strip()
                case_val = _restore(case_val)
                
                if case_val == "default":
                    if any(k in var_values for k in accumulated_cases):
                        return res_val
                        
                    default_res = res_val
                    has_default = True
                    accumulated_cases = []
                    default_pending = False
                else:
                    accumulated_cases.append(case_val)
                    if any(k in var_values for k in accumulated_cases):
                        return res_val
                        
                    if default_pending:
                        default_res = res_val
                        has_default = True
                        default_pending = False
                        
                    accumulated_cases = []
            else:
                case_val = choice.strip()
                case_val = _restore(case_val)
                
                if case_val == "default":
                    default_pending = True
                else:
                    accumulated_cases.append(case_val)

        if has_default:
            return default_res
        return ""
        
    return None
