# Task 02: restore blueprint middleware order

TraceForce is working in an older checkout of the `sanic` project. Blueprint middleware is registered in a sequence, and the request/response middleware around a blueprint must execute in the order promised by the framework's middleware semantics.

Investigate the blueprint registration path, the application middleware registry, and the existing test conventions. Fix the implementation so that middleware declared by a blueprint executes with the expected ordering for both request and response phases. Keep the change narrowly scoped and compatible with the existing API. Run the focused blueprint test and any additional local checks that help validate the behavior.

Do not copy a reference patch or modify the evaluation scripts. The Agent must reason from the repository and leave the generated workspace with the smallest maintainable production fix.
