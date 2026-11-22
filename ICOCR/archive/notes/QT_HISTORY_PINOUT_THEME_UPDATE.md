# History pinout selection and camera workspace background

- History tab now provides a package/reference dropdown above its pinout. It lists ICDB-linked references for the highlighted historical record.
- Changing the choice renders that reference in the History tab, without changing the currently selected Identify reference.
- The chosen reference identifier is retained on the history entry for the current application's session.
- Modern Light, Windows Classic and Warm Light themes use pure white (#FFFFFF) for the image viewer background and camera workspace, including letterboxed areas around the video.
- Dark, Graphite and Slate keep their existing dark viewer backgrounds. Button styling and scan behaviour are unchanged.

Validation: Python compilation and 4 tests with 6 subtests passed; 1 PySide6-dependent test skipped. Windows camera and interactive Qt GUI operation not tested here.
