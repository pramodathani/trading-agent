const PROVIDER_NAMES: Record<string, string> = {
  claude_code: 'Claude',
  deepseek: 'DeepSeek',
  ollama: 'Ollama',
  openai_compatible: 'OpenAI-compatible',
};

/** Turns model and provider identifiers into the names people read, such as "Haiku 5.5" for claude-haiku-5-5. */
export class ModelNames {
  /**
   * A model's readable name.
   * @param model The model's identifier or alias, such as "claude-haiku-5-5", "opus" or "deepseek-v4-pro".
   * @returns Such as "Haiku 5.5", "Opus" or "DeepSeek V4 Pro"; other names are returned unchanged.
   */
  label(model: string | null | undefined): string {
    if (!model) {
      return '';
    }
    const claude = /^claude-([a-z]+)-(\d+)-(\d+)$/.exec(model);
    if (claude !== null) {
      return `${this.capitalised(claude[1])} ${claude[2]}.${claude[3]}`;
    }
    if (['opus', 'sonnet', 'haiku', 'fable'].includes(model)) {
      return this.capitalised(model);
    }
    if (model.startsWith('deepseek-')) {
      const words = model
        .slice('deepseek-'.length)
        .split('-')
        .map((word) => (/^v\d/.test(word) ? word.toUpperCase() : this.capitalised(word)));
      return `DeepSeek ${words.join(' ')}`;
    }
    return model;
  }

  /**
   * A provider's readable name, from a backend's kind.
   * @param kind Such as "claude_code" or "deepseek".
   * @returns Such as "Claude" or "DeepSeek".
   */
  provider(kind: string): string {
    return PROVIDER_NAMES[kind] ?? kind;
  }

  /**
   * A word with its first letter in capitals.
   * @param word The word.
   * @returns The word, capitalised.
   */
  private capitalised(word: string): string {
    return word.charAt(0).toUpperCase() + word.slice(1);
  }
}

export const modelNames = new ModelNames();
