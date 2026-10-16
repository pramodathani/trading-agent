# tool.py

Each tool describes its arguments as a pydantic model. One definition then serves two purposes: `model_json_schema()` gives the JSON schema the AI model is shown, and `model_validate` checks the arguments the AI model sends before any code runs. Argument models use `extra='forbid'`, so a misspelt argument name is reported to the model instead of being ignored.

`input_schema` drops pydantic's `title` key and always includes `properties` and `required`, because some servers reject a schema without them.
