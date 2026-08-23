# Putting ductgen on a SolidWorks toolbar

`DuctGen.bas` is source, not a runnable macro — SolidWorks macros are `.swp`
files, which are binary VBA projects and cannot be committed to git in any
useful form. Building one takes about thirty seconds, once.

## Build the macro

1. Run `install.bat` in the repository root first, so Python and the
   dependencies are there.
2. In SolidWorks: **Tools → Macro → New…**, and save it as `DuctGen.swp`
   **inside this `macro\` folder**. The location matters — the macro locates
   the rest of the repository relative to itself.
3. The VBA editor opens with an empty `main`. Use **File → Import File…** and
   pick `DuctGen.bas` from this folder.
4. Delete the empty `Module1` that SolidWorks created, so `main` is not
   ambiguous.
5. Save (Ctrl+S) and close the editor.

## Put it on a button

**Tools → Customize → Commands → Macro**, drag the *New Macro Button* onto any
toolbar, and in the dialog point it at `macro\DuctGen.swp`, method
`DuctGen.main`. Give it a name and an icon.

That button now opens the ductgen window from inside SolidWorks. Set the prop,
motor and bed, press **Build in SolidWorks**, and the parts are created in the
session you are already in.

## If it does not start

The macro reports what it tried. The usual causes:

* **"Could not find ductgen-gui.pyw"** — the `.swp` is not in the repository's
  `macro\` folder. Move it there.
* **"Could not start Python"** — Python is not on PATH. Either re-install it
  with *Add python.exe to PATH* ticked, or create a virtualenv at the
  repository root (`python -m venv .venv` then
  `.venv\Scripts\pip install -r requirements.txt`); the macro checks
  `.venv\Scripts\pythonw.exe` before it falls back to PATH.

## Why a launcher and not a pure VBA tool

The geometry engine could have been written in VBA and needed no Python at
all. It is not, for two reasons: the same engine has to run headless in CI to
render preview images and check the design rules on every commit, and a VBA
module cannot be unit-tested or diffed sensibly. The Python core is the tool;
this macro is the door into it from SolidWorks.
