/** What a difference view shows. */
export interface DiffViewProperties {
  difference: string;
}

/**
 * Shows a unified diff with added lines in green and removed lines in red.
 * @param properties The diff text.
 * @returns The view.
 */
export function DiffView(properties: DiffViewProperties) {
  if (!properties.difference.trim()) {
    return <p className="muted small">No difference: the proposal matches the file as it is.</p>;
  }
  const lines = properties.difference.split('\n');
  return (
    <pre className="diff">
      {lines.map((line, index) => {
        let lineClass = 'diff-line';
        if (line.startsWith('+') && !line.startsWith('+++')) {
          lineClass = 'diff-line added';
        } else if (line.startsWith('-') && !line.startsWith('---')) {
          lineClass = 'diff-line removed';
        } else if (line.startsWith('@@')) {
          lineClass = 'diff-line hunk';
        }
        return (
          <span key={index} className={lineClass}>
            {line}
            {'\n'}
          </span>
        );
      })}
    </pre>
  );
}
