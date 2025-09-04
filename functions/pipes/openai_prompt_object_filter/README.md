# OpenAI Prompt Object Filter

Adds support for OpenAI’s **Prompt Object** in the Responses API, letting you replace inline system prompts with a saved prompt reference from the [OpenAI dashboard](https://platform.openai.com/chat).

* If `prompt` is present in the body → system messages are removed, and the `prompt` object is passed through unchanged.
* If `prompt` is not present → the request is forwarded unchanged.

## Setup Instructions (Open WebUI)

1. **Admin Panel ▸ Functions ▸ Import from Link**

   * Main (stable):
     `https://github.com/jrkropp/open-webui-developer-toolkit/blob/main/functions/pipes/openai_prompt_object_filter/openai_prompt_object_filter.py`
   * Alpha (preview):
     `https://github.com/jrkropp/open-webui-developer-toolkit/blob/alpha-preview/functions/pipes/openai_prompt_object_filter/openai_prompt_object_filter.py`

2. Enable **Global** for the filter (⋯ menu → Global).

3. Ensure the filter is toggled **on**.

4. Go to **Admin Panel ▸ Models**, edit your model, and under **Advanced Parameters**, add a custom parameter named `prompt` with:

   ```json
   {
     "id": "pmpt_abc123",
     "version": "1"
   }
   ```
