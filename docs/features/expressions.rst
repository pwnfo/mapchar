Expressions & Classes
=====================

At the core of Mapchar is the expression parser. 

Literal Characters
------------------
Literal characters produce themselves. For example, ``admin`` literally yields ``admin``. If you concatenate it with numbers, it produces combinations.

.. code-block:: bash
   
   $ mapchar 'admin/d'
   admin0
   admin1
   ...
   admin9

Built-in Character Classes
--------------------------
To easily reference standard character sets, Mapchar provides built-in tokens initialized with a forward slash ``/``.

========= ======================== =====================================
Symbol    Meaning                  Example / Resulting Output          
========= ======================== =====================================
``/l``    Letters                  ``a–z`` and ``A–Z``
``/a``    Lowercase letters        ``a–z``
``/A``    Uppercase letters        ``A–Z``
``/d``    Digits                   ``0–9``
``/D``    Non-zero digits          ``1–9``
``/h``    Hexadecimal (lower)      ``0–9``, ``a–f``
``/H``    Hexadecimal (upper)      ``0–9``, ``A–F``
``/s``    Whitespace               (Space)
``/o``    Octal digits             ``0–7``
``/p``    Special characters       ``!@#$%^&*-_+=``
``/b``    Newline                  ``\n``
========= ======================== =====================================

Custom Classes and Unions
-------------------------
You can construct your own custom character classes by wrapping items in brackets ``[...]``.
For example, ``[abc]`` generates the characters ``a``, ``b``, or ``c``.

**Mixing Built-in Classes inside Brackets**
Built-in tokens naturally expand *inside* brackets.

.. code-block:: bash

   $ mapchar '[/d/a_]'
   # Yields all digits, lowercase letters, and underscores: 0, 1..., a, b..., _

**Unions (Alternatives)**
Use the pipe character ``|`` to separate full-word alternatives inside brackets. Each option acts as a discrete, indivisible block.

.. code-block:: bash
   
   $ mapchar '[admin|root|123]'
   admin
   root
   123

This allows grouping multiple payloads logically.

Literal Groups
--------------
If you need an entire word sequence to be treated strictly as a single permutation unit without interpreting inner unions, you can wrap it in literal parenthesis ``(...)``. This is highly useful when combined with quantifiers.

.. code-block:: bash

   $ mapchar '(admin){3}'
   adminadminadmin

Quantifiers
-----------
Control repetition using brace syntax. The syntax supports minimum and maximum repetitions.

* ``{N}`` — Repeat exactly **N** times.
* ``{min,max}`` — Repeat between **min** and **max** times (inclusive).
* ``?`` — Sugar syntax for exactly **0 or 1** time (optional).

Examples:

.. code-block:: bash

   $ mapchar '[XYZ]{3}'
   # Yields: XXX, XXY, XXZ, XYX... (27 permutations)

   $ mapchar '[XYZ]{1,2}'
   # Yields: X, Y, Z, XX, XY, XZ... (12 permutations)

   $ mapchar '(admin)?[12]'
   # Yields: 1, 2, admin1, admin2

Expression Alternation
----------------------
You can combine multiple independent expressions in a single line or template using the double-pipe operator ``||``. This is useful for generating wordlists from disparate patterns without creating separate files.

.. code-block:: bash

   $ mapchar 'admin/d{2}||guest/d{2}'
   # Yields: admin00, admin01... guest98, guest99...

Unlike the single pipe ``|`` inside brackets (which works at the character/class level), the double pipe ``||`` operates at the top level of the generator, effectively chaining full expressions together.

Escaping
--------
Need to output a reserved token like ``/d``, ``[``, ``}``, or ``^``? Escape it using a backslash ``\``.

.. code-block:: bash

   $ mapchar '\/d/d'
   /d0
   /d1
   ...
