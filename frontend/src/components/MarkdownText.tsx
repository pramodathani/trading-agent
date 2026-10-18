import hljs from 'highlight.js/lib/core';
import bash from 'highlight.js/lib/languages/bash';
import diff from 'highlight.js/lib/languages/diff';
import ini from 'highlight.js/lib/languages/ini';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import markdown from 'highlight.js/lib/languages/markdown';
import python from 'highlight.js/lib/languages/python';
import shell from 'highlight.js/lib/languages/shell';
import sql from 'highlight.js/lib/languages/sql';
import typescript from 'highlight.js/lib/languages/typescript';
import xml from 'highlight.js/lib/languages/xml';
import yaml from 'highlight.js/lib/languages/yaml';
import { type ComponentProps, type MouseEvent, type ReactNode, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { appFiles } from '../utilities/appFiles';
import { platform } from '../utilities/platform';

const COPIED_MILLISECONDS = 1500;
const REMARK_PLUGINS = [
  remarkGfm,
];

hljs.registerLanguage('bash', bash);
hljs.registerLanguage('diff', diff);
hljs.registerLanguage('ini', ini);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('json', json);
hljs.registerLanguage('markdown', markdown);
hljs.registerLanguage('python', python);
hljs.registerLanguage('shell', shell);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('yaml', yaml);
hljs.registerAliases(
  [
    'sh',
    'zsh',
    'console',
  ],
  {
    languageName: 'bash',
  },
);
hljs.registerAliases(
  [
    'toml',
  ],
  {
    languageName: 'ini',
  },
);

/** What the Markdown view shows. */
interface MarkdownTextProperties {
  text: string;
}

/**
 * A desk's reply rendered as Markdown, the way Claude Code shows answers: headings, lists, tables, links, inline code and highlighted code blocks with a copy button. Raw HTML in the text is shown as text, never run.
 * @param properties The Markdown text.
 * @returns The rendered reply.
 */
export function MarkdownText(properties: MarkdownTextProperties) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        components={{
          a: MarkdownLink,
          pre: CodeBlock,
          table: MarkdownTable,
        }}
      >
        {properties.text}
      </ReactMarkdown>
    </div>
  );
}

/**
 * A link that opens in a new tab, so the chat stays where it is.
 * @param properties The link's attributes and text.
 * @returns The link.
 */
function MarkdownLink(properties: ComponentProps<'a'>) {
  /**
   * Inside the app, opens the link in an in-app browser sheet instead of a new tab.
   * @param click The click on the link.
   */
  function openInApp(click: MouseEvent): void {
    if (!platform.isApp() || !properties.href) {
      return;
    }
    click.preventDefault();
    void appFiles.openLink(properties.href);
  }

  return (
    <a href={properties.href} target="_blank" rel="noreferrer noopener" onClick={openInApp}>
      {properties.children}
    </a>
  );
}

/**
 * A table inside a rounded, scrollable frame.
 * @param properties The table's children.
 * @returns The framed table.
 */
function MarkdownTable(properties: ComponentProps<'table'>) {
  return (
    <div className="markdown-table">
      <table>{properties.children}</table>
    </div>
  );
}

/**
 * A fenced code block with its language and a copy button above it, coloured by highlight.js when the language is one it knows.
 * @param properties The block's children: a code element whose class names the language and whose child is the code.
 * @returns The block.
 */
function CodeBlock(properties: ComponentProps<'pre'>) {
  const [copied, setCopied] = useState(false);
  const language = languageOf(properties.children);
  const code = codeOf(properties.children);
  const coloured = useMemo(() => {
    if (language === 'text' || hljs.getLanguage(language) === undefined) {
      return null;
    }
    return hljs.highlight(code, {
      language,
      ignoreIllegals: true,
    }).value;
  }, [
    code,
    language,
  ]);

  /** Copies the block's text and shows "Copied" for a moment. */
  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), COPIED_MILLISECONDS);
  }

  return (
    <div className="code-block">
      <div className="code-block-header">
        <span>{language}</span>
        <button type="button" className="code-block-copy" onClick={() => void copy()} aria-label="Copy the code">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre>{coloured === null ? <code>{code}</code> : <code className="hljs" dangerouslySetInnerHTML={{ __html: coloured }} />}</pre>
    </div>
  );
}

/**
 * The code element's own properties, when the pre element holds one.
 * @param children The pre element's children.
 * @returns The code element's className and children, or null.
 */
function codeProperties(children: ReactNode): { className?: string; children?: ReactNode } | null {
  if (children === null || typeof children !== 'object' || !('props' in children)) {
    return null;
  }
  return children.props as { className?: string; children?: ReactNode };
}

/**
 * Reads the language from a code block, such as "python" from "language-python".
 * @param children The pre element's children.
 * @returns The language in lower case, or "text" when none was given.
 */
function languageOf(children: ReactNode): string {
  const match = /language-([\w+#-]+)/.exec(codeProperties(children)?.className ?? '');
  return match === null ? 'text' : match[1].toLowerCase();
}

/**
 * Reads a code block's text, without the newline Markdown leaves at its end.
 * @param children The pre element's children.
 * @returns The code.
 */
function codeOf(children: ReactNode): string {
  const inner = codeProperties(children)?.children;
  const text = Array.isArray(inner) ? inner.join('') : String(inner ?? '');
  return text.replace(/\n$/, '');
}
