# Third-party notices

## Chinook sample database

`src/intellectaengine/assets/Chinook.db` is the Chinook sample music-store database maintained by
[Luis Rocha](https://github.com/lerocha/chinook-database).

On 2026-09-24, all rows in the bundled file's 11 application tables were compared
with the public [v1.4.5 SQLite release](https://github.com/lerocha/chinook-database/releases/tag/v1.4.5).
The table contents match `Chinook_Sqlite.sqlite`. The database files are **not
byte-identical**; this is a content verification, not a claim about the original
download or SQLite file layout.

Bundled file SHA-256:

```text
84f5d9143ac4deebdb81650ab650e226d909e660106846b119a5c47c33f94c13
```

The [upstream data description](https://github.com/lerocha/chinook-database/tree/v1.4.5#sample-data)
states that customer and employee names are fictitious, contact information is
sample data, and sales are generated. Music catalogue information comes from an
iTunes library. Do not replace this fixture with personal or business records.

The following notice is reproduced from the
[upstream v1.4.5 license](https://github.com/lerocha/chinook-database/blob/v1.4.5/LICENSE.md):

```text
Chinook Database
--------------------------------------
Copyright (c) 2008-2024 Luis Rocha

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## Python dependencies

Dependencies retain their own licenses. `uv.lock` records their resolved versions
and distribution hashes. Model weights downloaded separately by embedding
providers are not bundled; their upstream model licenses also apply.
