fn main() -> Result<(), Box<dyn std::error::Error>> {
    let files = [
        "../../proto/kolibri.v1.proto",
        "../../proto/agent.v1.proto",
        "../../proto/node.v1.proto",
        "../../proto/task.v1.proto",
        "../../proto/event.v1.proto",
        "../../proto/terminal.v1.proto",
    ];

    let config = tonic_build::configure();
    config.compile_protos(&files, &["../../proto"])?;
    Ok(())
}
