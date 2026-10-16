# configuration_loader.py

The three ways reading can fail (missing file, invalid TOML, invalid values) all become one `ConfigurationError`, so the application has a single place to print the message and stop with exit status 2. The message always names the file, because with several projects on the machine it is easy to be editing the wrong one.

`tomllib` comes from the standard library, so reading the configuration needs no extra package.
