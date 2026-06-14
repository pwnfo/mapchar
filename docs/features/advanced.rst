Advanced Concepts
=================

Expression Files (.mapc)
------------------------
For very complex generations, you can author ``.mapc`` files instead of invoking the CLI. These files allow defining explicit aliases and sequentially joining outputs from multiple sub-expressions. 

**Syntax Overview**

- Comments start with ``"# "`` (hash followed by a space) at the beginning of a line, or ``" # "`` (space + hash + space) when used inline.
- ``%define name pattern``: Replace ``$name;`` with ``pattern`` throughout the rest of the file.
- ``%include filename.txt``: Expressly opens a file relative to the ``.mapc`` script or an absolute path.
- **Important**: When you declare a ``%include``, that file is bound to the ``^`` placeholder in the **very next expression line**. It does not persist globally. You can declare multiple ``%define`` lines consecutively to bind to multiple ``^`` placeholders in the next expression.
- Any other (non-empty) line is treated as an expression.

**Example payloads.mapc**:

.. code-block:: text

   # Define Reusable Payload Aliases
   %define DIGIT #[0-9]
   %define BASE_URL (https://example.com/api/)
   
   # Include a dictionary text file from previous runs
   %include default_paths.txt

   # Expression Generation
   $BASE_URL;^\?id=$DIGIT; # Example: https://example.com/api/account?id=1
   $BASE_URL;v$DIGIT; # Example: https://example.com/api/v1

Run using ``-f`` or ``--file``:

.. code-block:: bash

   mapchar -f payloads.mapc

Smart Skipping & Chunking
-------------------------
Large permutations quickly hit constraints. Mapchar addresses this through algorithmic seeking. Instead of creating combinations starting from `A` waiting until it hits your target, Mapchar calculates precisely where a specific target begins and resumes generation from there optimally.

You can segment workloads using ``-s/--start`` and ``-e/--end``.

.. code-block:: bash

   $ mapchar '/l{4}' -s abcd -e wxyz
   abcd
   abce
   abcf
   ...
   wxyz

This logic applies cleanly natively even when distributing across threads.

Multi-threading
---------------------------
You can specify multiple workers via ``-w <int>``. 
Mapchar intelligently delegates disjoint segments of the permutation space to each worker.

.. code-block:: bash
   
   # using 3 different workers to write
   $ mapchar '[/l/d]{5}' -w 3 -o output.txt


Value Bindings
--------------
Value bindings let you evaluate an expression **once per output line** and reuse the result any number of times within that line.
Without bindings, two tokens always expand via cartesian product.
With bindings, a definition and its references share the same drawn value — no additional combinations are introduced.

**Syntax Overview**

- ``<@name=expr>`` — evaluate ``expr``, store the result under ``name``, and output it.
- ``<@name>`` — output the value previously stored under ``name``.

``name`` must be a valid Python identifier. Referencing a name before it is defined raises an error.

**Basic example**

.. code-block:: bash

   $ mapchar '<@d=/d>-<@d>'
   0-0
   1-1
   ...
   9-9

Naively writing ``/d-/d`` would produce 100 lines (cartesian product of two independent digits).
With a binding, the digit is picked once and reused — 10 lines.

**File placeholders inside bindings**

The ``^`` placeholder works inside ``<@name=^>``:

.. code-block:: bash

   $ mapchar '<@x=^>:<@x>' words.txt
   # apple:apple
   # banana:banana

**Repetition on bindings**

Quantifiers ``{N}``, ``{min,max}``, and ``?`` work on both definitions and references.

*Repetition on the definition* — the inner expression is repeated N times before being stored:

.. code-block:: bash

   $ mapchar '<@n=/d{2}>_<@n>'
   00_00
   01_01
   ...
   99_99

*Repetition on the reference* — the stored value is repeated N times in-place:

.. code-block:: bash

   $ mapchar '<@d=/d>_<@d>{2}'
   0_00
   1_11
   ...
   9_99

**Multiple bindings**

Each ``<@name=expr>`` is independent. Their values are combined via cartesian product with each other, but each pair of ``<@name=expr>`` / ``<@name>`` is internally consistent:

.. code-block:: bash

   $ mapchar '<@a=[01]><@b=[xy]><@a><@b>'
   0x0x
   0y0y
   1x1x
   1y1y
