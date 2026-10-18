"""Turns model ids and backend kinds into the names the web page shows.

It is a port of the web page's modelNames.ts.

Typical usage example:

  names = ModelNames()
  names.label('claude-sonnet-4-6')  # 'Sonnet 4.6'
  names.provider('claude_code')  # 'Claude'
"""

import re

_PROVIDER_NAMES = {
    'claude_code': 'Claude',
    'deepseek': 'DeepSeek',
    'ollama': 'Ollama',
    'openai_compatible': 'OpenAI-compatible',
}
_CLAUDE_ALIASES = (
    'opus',
    'sonnet',
    'haiku',
    'fable',
)
_CLAUDE_MODEL = re.compile(r'^claude-([a-z]+)-(\d+)-(\d+)$')
_VERSION_WORD = re.compile(r'^v\d')


class ModelNames:
    """Readable names for models and providers."""

    def label(self, model: str | None) -> str:
        """A model's readable name.

        Args:
            model (str | None): The model id, such as "claude-opus-4-1" or "deepseek-v4-pro".

        Returns:
            str: Such as "Opus 4.1" or "DeepSeek V4 Pro", the id itself when it has no special form, or an empty string for None.
        """
        if not model:
            return ''
        claude = _CLAUDE_MODEL.match(model)
        if claude is not None:
            return f'{claude.group(1).capitalize()} {claude.group(2)}.{claude.group(3)}'
        if model in _CLAUDE_ALIASES:
            return model.capitalize()
        if model.startswith('deepseek-'):
            words = []
            for word in model[len('deepseek-') :].split('-'):
                if _VERSION_WORD.match(word):
                    words.append(word.upper())
                else:
                    words.append(word.capitalize())
            return 'DeepSeek ' + ' '.join(words)
        return model

    def provider(self, kind: str) -> str:
        """A backend kind's provider name.

        Args:
            kind (str): The backend kind, such as "claude_code".

        Returns:
            str: Such as "Claude", or the kind itself when unknown.
        """
        return _PROVIDER_NAMES.get(kind, kind)
