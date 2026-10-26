# domain-architecture/events/

Event contract YAML specs for integration events that cross bounded context boundaries.

Each spec is a machine-checkable description of the payload a producer emits and a consumer depends on. The narrative for these events lives in [`../DOMAIN-EVENTS.md`](../DOMAIN-EVENTS.md).

No event contracts are finalised yet. The first candidates are `ScreeningRequested` and `VerdictIssued`, both of which will get a spec here once their payloads stabilise. Contract-conformance tests belong in the project test suite.
