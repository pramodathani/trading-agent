# Loadable.tsx

Every polled section shows the same three states: loading, an error when nothing has loaded yet, and the content. After a first success, a later failed refresh keeps showing the last content rather than replacing it with an error.
