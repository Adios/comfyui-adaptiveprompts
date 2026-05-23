# plugin_registry.py

class PluginRegistry:
    """
    A minimal, scalable registry for extending the core parsing engine without modifying core loops.
    Designed with future expansion in mind (e.g., file_loading_hooks, post_evaluation_hooks can be added here cleanly).
    """
    
    bracket_handlers = []
    wildcard_handlers = []

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
