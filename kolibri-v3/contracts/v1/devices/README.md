# Kolibri device contracts

`device-capability-manifest.schema.json` is the first versioned boundary for a
Kolibri device to declare its physical/runtime capabilities.

The declaration is untrusted input. Product/Data must combine it with verified
runtime evidence, tenant policy, user authorization and vertical entitlements
before returning an effective capability snapshot.

The manifest does not:

- enroll or authenticate a device;
- grant a permission;
- attest hardware;
- enable a vertical pack;
- authorize an agent or hardware command;
- carry credentials or arbitrary executable code.

The example directory contains representative declarations. Contract versions
are independent from a Tauri, React Native, browser or device SDK release.

