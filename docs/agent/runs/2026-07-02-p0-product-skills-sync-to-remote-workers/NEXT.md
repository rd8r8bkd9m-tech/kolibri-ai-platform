# NEXT

Recommended follow-ups:

1. Add a Control Plane task kind that invokes `ops/skill_sync.py install/update`
   on selected workers and stores the proof JSON under the task artifact root.
2. Add registry publication to the release train so all workers receive the same
   local registry/source bundle before sync.
3. Add an operator canary that installs one small test skill on a non-critical
   worker and collects the proof artifact.

