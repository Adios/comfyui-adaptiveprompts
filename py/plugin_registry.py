# plugin_registry.py

class PluginRegistry:
    """
    A minimal, scalable registry for extending the core parsing engine without modifying core loops.
    Designed with future expansion in mind (e.g., file_loading_hooks, post_evaluation_hooks can be added here cleanly).
    """
    
    bracket_handlers = []
    wildcard_handlers = []
    bypass_handlers = []

    @classmethod
    def register_bracket_handler(cls, handler):
        """
        Registers a function to intercept {bracket} parsing.
        Signature: handler(content: str, rng: SeededRandom, wildcard_dir: str, resolved_vars: dict) -> str | None
        Return a string to replace the bracket, or None to let default core logic handle it.
        """
        cls.bracket_handlers.append(handler)

    @classmethod
    def register_wildcard_handler(cls, handler):
        """
        Registers a function to intercept __wildcard__ parsing.
        Signature: handler(full_token: str, wc_name: str, var_tok: str, rng: SeededRandom, wildcard_dir: str, resolved_vars: dict) -> str | None
        Return a string to replace the wildcard, or None to let default core logic handle it.
        """
        cls.wildcard_handlers.append(handler)

    @classmethod
    def dispatch_bracket(cls, content: str, rng, wildcard_dir: str, resolved_vars: dict) -> str | None:
        for handler in cls.bracket_handlers:
            result = handler(content, rng, wildcard_dir, resolved_vars)
            if result is not None:
                return result
        return None

    @classmethod
    def dispatch_wildcard(cls, full_token: str, wc_name: str, var_tok: str, rng, wildcard_dir: str, resolved_vars: dict) -> str | None:
        for handler in cls.wildcard_handlers:
            result = handler(full_token, wc_name, var_tok, rng, wildcard_dir, resolved_vars)
            if result is not None:
                return result
        return None

    @classmethod
    def register_bypass_handler(cls, handler):
        """
        Registers a function to intercept bracket splitting bypass checks.
        Signature: handler(content: str) -> bool
        Return True if the bracket should be treated as literal text and not split.
        """
        cls.bypass_handlers.append(handler)

    @classmethod
    def is_bypassed(cls, content: str) -> bool:
        """
        Queries all registered bypass handlers. Returns True if any handler claims the bracket.
        Example: if a user feeds `{switch(view) | close-up: face | default: shoes}`, the Sequencer 
        will normally violently chop it into three separate outputs. By bypassing this, the Sequencer 
        knows to leave the entire string intact as a literal.
        """
        for handler in cls.bypass_handlers:
            if handler(content):
                return True
        return False
