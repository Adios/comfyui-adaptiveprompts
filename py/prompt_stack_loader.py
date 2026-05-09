import os
import re
from typing import List
from .generator import resolve_wildcards, SeededRandom, DEFAULT_WILDCARD_ROOT
from .wildcard_utils import _normalize_input_context, _ensure_bucket_dict

DEFAULT_PROMPT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "prompts")
)

class PromptStackLoader:
    """
    Sequentially loads, parses, and evaluates a stack of text files,
    stripping LoRA tags, evaluating prompts, and accumulating an Adaptive Prompts context.
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_dir": ("STRING", {
                    "default": "",
                    "tooltip": "The root directory for your stack. Absolute paths work. Relative paths anchor to this custom node's root directory. Leave empty to default to the 'prompts' folder."
                }),
                "stack_file": ("STRING", {
                    "default": "",
                    "tooltip": "Optional. Path to a .txt file containing your stack. Absolute paths work. Relative paths (e.g., 'stacks/my_stack.txt') resolve against base_dir."
                }),
                "inline_stack": ("STRING", {
                    "multiline": True, 
                    "default": "",
                    "tooltip": "List of text paths to load sequentially (absolute paths work, relative resolve against base_dir).\n- Use 'random:folder' to pick a random file.\n- Prefix with 'remove:' to exclude a path.\n- Use 'replace:old|new' to swap a path in-place.\n- Lines starting with # are ignored."
                }),
                "override_context": ("BOOLEAN", {
                    "default": False, 
                    "label_on": "Override", 
                    "label_off": "Merge",
                    "tooltip": "Override: New variables replace old ones. Merge: New variables are combined into existing buckets."
                }),
                "seed": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "max": 0xffffffffffffffff,
                    "tooltip": "Controls the random file selection for 'random:' paths and internal wildcards."
                }),
            },
            "optional": {
                "context": ("DICT", {
                    "tooltip": "Optional upstream context to build upon."
                }),
            },
        }
        
    RETURN_TYPES = ("STRING", "DICT", "STRING")
    RETURN_NAMES = ("prompt", "context", "lora_string")
    FUNCTION = "process"
    CATEGORY = "adaptiveprompts/generation"

    def _resolve_paths(self, base_dir: str, stack_file: str, inline_stack: str) -> List[str]:
        paths = []
        if stack_file:
            # We use the variable 'stack_path' instead of the old 'config_path'
            stack_path = stack_file
            if not os.path.isabs(stack_path) and base_dir:
                stack_path = os.path.normpath(os.path.join(base_dir, stack_path))
            try:
                with open(stack_path, "r", encoding="utf-8") as f:
                    paths.extend(f.readlines())
            except OSError as e:
                print(f"[Adaptive Prompts] Warning: Could not read stack file '{stack_path}': {e}")

        if inline_stack:
            paths.extend(inline_stack.splitlines())
            
        return paths

    def _get_random_file(self, dir_path: str, rng: SeededRandom) -> str:
        candidates = []
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.lower().endswith(".txt"):
                    candidates.append(os.path.join(root, file))
        if candidates:
            return rng.choice(candidates)
        return ""

    def process(self, seed: int, base_dir: str, stack_file: str, inline_stack: str, override_context: bool = False, context: dict = None):
        rng = SeededRandom(seed)
        
        resolved_base_dir = base_dir.strip()
        if not resolved_base_dir:
            resolved_base_dir = DEFAULT_PROMPT_ROOT
        elif not os.path.isabs(resolved_base_dir):
            # Anchor relative base_dir to the custom node's root directory.
            # This allows portable paths like "prompts/arch" to resolve properly.
            node_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            resolved_base_dir = os.path.normpath(os.path.join(node_root, resolved_base_dir))
            
        raw_lines = self._resolve_paths(resolved_base_dir, stack_file, inline_stack)
        
        def _normalize_match(p: str) -> str:
            # Normalizes slashes and redundant ./ for cross-platform string matching.
            is_rand = p.startswith("random:")
            core = p[7:].strip() if is_rand else p
            core = os.path.normpath(core).replace("\\", "/")
            return f"random:{core}" if is_rand else core
        
        # Pass 1 (Identify Modifiers)
        exclusions = set()
        swaps = {}
        for line in raw_lines:
            clean_line = line.strip()
            if clean_line.startswith("remove:"):
                path_to_exclude = clean_line[7:].strip()
                if path_to_exclude:
                    exclusions.add(_normalize_match(path_to_exclude))
            elif clean_line.startswith("replace:"):
                # Slice off 'replace:' and split by the first pipe
                parts = clean_line[8:].split("|", 1)
                if len(parts) == 2:
                    old_path = parts[0].strip()
                    new_path = parts[1].strip()
                    if old_path and new_path:
                        swaps[_normalize_match(old_path)] = new_path

        # Pass 2 (Filter and Swap the Stack)
        valid_lines = []
        unused_exclusions = exclusions.copy()
        unused_swaps = set(swaps.keys())
        
        for line in raw_lines:
            clean_line = line.strip()
            # Skip empty lines, comments, and the modifier commands themselves
            if not clean_line or clean_line.startswith("#") or clean_line.startswith("remove:") or clean_line.startswith("replace:"):
                continue
                
            match_key = _normalize_match(clean_line)
                
            # Handle Exclusions
            if match_key in exclusions:
                if match_key in unused_exclusions:
                    unused_exclusions.remove(match_key)
                continue
                
            # Handle Swaps
            if match_key in swaps:
                valid_lines.append(swaps[match_key])
                if match_key in unused_swaps:
                    unused_swaps.remove(match_key)
                continue
                
            # If not modified, keep the original line
            valid_lines.append(line)

        # Pass 3 (Typo Check / Debug Warning)
        for unused in unused_exclusions:
            print(f"[Adaptive Prompts] Debug: Exclusion target '{unused}' did not match any loaded paths.")
        for unused in unused_swaps:
            print(f"[Adaptive Prompts] Debug: Swap target '{unused}' -> '{swaps[unused]}' did not match any loaded paths.")

        files_to_process = []
        for line in valid_lines:
            line = line.strip()
            # We already filtered empty and # lines, but we re-strip for safety
            if not line or line.startswith("#"):
                continue
                
            is_random = line.startswith("random:")
            path_str = line[len("random:"):].strip() if is_random else line
            
            resolved_path = path_str
            if not os.path.isabs(resolved_path):
                resolved_path = os.path.normpath(os.path.join(resolved_base_dir, resolved_path))
                
            if is_random and os.path.isdir(resolved_path):
                chosen_file = self._get_random_file(resolved_path, rng)
                if chosen_file:
                    files_to_process.append(chosen_file)
            else:
                if os.path.isfile(resolved_path):
                    files_to_process.append(resolved_path)
                else:
                    print(f"[Adaptive Prompts] Warning: Path '{resolved_path}' is not a valid file.")

        current_context = {}
        if context is not None:
            current_context = _normalize_input_context(context)
        
        lora_tags = []
        accumulated_prompts = []
        lora_regex = re.compile(r"<lora:[^>]+>")

        for filepath in files_to_process:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError as e:
                print(f"[Adaptive Prompts] Warning: Failed to read file '{filepath}': {e}")
                continue
                
            found_loras = lora_regex.findall(content)
            lora_tags.extend(found_loras)
            cleaned_content = lora_regex.sub("", content)
            
            cleaned_content = re.sub(r",\s*,", ",", cleaned_content)
            cleaned_content = re.sub(r"^\s*,\s*", "", cleaned_content)
            cleaned_content = re.sub(r"\s*,\s*$", "", cleaned_content)
            cleaned_content = " ".join(cleaned_content.split())
            
            snapshot = {}
            if override_context:
                for k, v in current_context.items():
                    if isinstance(v, dict):
                        snapshot[k] = list(v.keys())

            # Evaluate text and capture the prompt string
            evaluated_text = resolve_wildcards(
                cleaned_content,
                rng,
                DEFAULT_WILDCARD_ROOT,
                _resolved_vars=current_context
            )
            
            if evaluated_text.strip():
                accumulated_prompts.append(evaluated_text.strip())
            
            if override_context:
                for k, old_keys in snapshot.items():
                    if k in current_context and isinstance(current_context[k], dict):
                        current_keys = list(current_context[k].keys())
                        new_keys = [key for key in current_keys if key not in old_keys]
                        if new_keys:
                            for old_k in old_keys:
                                del current_context[k][old_k]
            
        for k, v in list(current_context.items()):
            if not isinstance(v, dict):
                current_context[k] = _ensure_bucket_dict(v)

        lora_string = " ".join(lora_tags)
        final_prompt_string = ", ".join(accumulated_prompts)
        
        return (final_prompt_string, current_context, lora_string)
