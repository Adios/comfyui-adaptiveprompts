import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const ID_PREFIX = "AdaptivePrompts.";

// Syncs the UI change to the Python backend immediately
async function syncToBackend(key, value) {
    try {
        await api.fetchApi("/adaptive_prompts/config", {
            method: "POST",
            body: JSON.stringify({ [key]: value })
        });
    } catch (e) {
        console.error("[Adaptive Prompts] Failed to sync config:", e);
    }
}

app.registerExtension({
    name: "AdaptivePrompts.Settings",
    async setup() {
        // 1. Fetch the initial state from Python so the UI matches the JSON
        let currentConfig = {};
        try {
            const response = await api.fetchApi("/adaptive_prompts/config");
            currentConfig = await response.json();
        } catch (e) {
            console.error("[Adaptive Prompts] Failed to fetch initial config", e);
        }

        // 2. Build the UI widgets
        app.ui.settings.addSetting({
            id: ID_PREFIX + "resolution_strategy",
            name: "Adaptive Prompts: Resolution Strategy",
            type: "combo",
            options: ["Global first", "Local first"],
            defaultValue: currentConfig.resolution_strategy ?? "Global first",
            onChange: (value) => syncToBackend("resolution_strategy", value)
        });

        app.ui.settings.addSetting({
            id: ID_PREFIX + "search_depth_limit",
            name: "Adaptive Prompts: Search Depth Limit",
            type: "slider",
            attrs: { min: 10, max: 200, step: 1 },
            defaultValue: currentConfig.search_depth_limit ?? 80,
            onChange: (value) => syncToBackend("search_depth_limit", value)
        });

        app.ui.settings.addSetting({
            id: ID_PREFIX + "default_rng_mode",
            name: "Adaptive Prompts: Default RNG Mode",
            type: "combo",
            options: ["Signature", "Classic"],
            defaultValue: currentConfig.default_rng_mode ?? "Signature",
            onChange: (value) => syncToBackend("default_rng_mode", value)
        });

        app.ui.settings.addSetting({
            id: ID_PREFIX + "hide_comments",
            name: "Adaptive Prompts: Hide Comments by Default",
            type: "boolean",
            defaultValue: currentConfig.hide_comments ?? true,
            onChange: (value) => syncToBackend("hide_comments", value)
        });
    }
});