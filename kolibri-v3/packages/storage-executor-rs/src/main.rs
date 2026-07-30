use std::env;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::ExitCode;

use kolibri_storage_executor::{
    Engine, ErrorBody, ErrorEnvelope, ExecutorError, PROTOCOL_V1, RequestEnvelope,
    ResponseEnvelope, VerifiedPolicy,
};

struct Config {
    policy_path: PathBuf,
    public_key_hex: String,
    state_db_path: PathBuf,
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            let response = ErrorEnvelope {
                protocol_version: PROTOCOL_V1,
                request_id: "bootstrap".to_owned(),
                ok: false,
                error: ErrorBody::from(&error),
            };
            let _ = write_response(&response);
            ExitCode::from(78)
        }
    }
}

fn run() -> kolibri_storage_executor::Result<()> {
    let config = parse_args()?;
    let policy = VerifiedPolicy::load(&config.policy_path, &config.public_key_hex)?;
    let engine = Engine::with_system_clock(policy, &config.state_db_path)?;
    let maximum = usize::try_from(engine.max_request_bytes()).map_err(|_| {
        ExecutorError::rejected(
            "request_limit_invalid",
            "The configured request limit is invalid.",
        )
    })?;
    let mut body = Vec::with_capacity(maximum.min(64 * 1024));
    std::io::stdin()
        .take((maximum as u64).saturating_add(1))
        .read_to_end(&mut body)?;
    if body.is_empty() || body.len() > maximum {
        return write_protocol_error(
            "invalid",
            ExecutorError::rejected(
                "request_size_invalid",
                "The protocol request is empty or too large.",
            ),
        );
    }
    let request: RequestEnvelope = match serde_json::from_slice(&body) {
        Ok(request) => request,
        Err(_) => {
            return write_protocol_error(
                "invalid",
                ExecutorError::rejected(
                    "request_json_invalid",
                    "The protocol request JSON is invalid.",
                ),
            );
        }
    };
    if request.protocol_version != PROTOCOL_V1 {
        return write_protocol_error(
            &request.request_id,
            ExecutorError::rejected(
                "protocol_version_unsupported",
                "The protocol version is unsupported.",
            ),
        );
    }
    match engine.handle(&request.request_id, &request.command) {
        Ok(result) => write_response(&ResponseEnvelope {
            protocol_version: PROTOCOL_V1,
            request_id: request.request_id,
            ok: true,
            result,
        }),
        Err(error) => write_protocol_error(&request.request_id, error),
    }
}

fn parse_args() -> kolibri_storage_executor::Result<Config> {
    let mut args = env::args_os();
    let _program = args.next();
    let mut policy_path = None;
    let mut public_key_hex = None;
    let mut state_db_path = None;
    while let Some(argument) = args.next() {
        match argument.to_str() {
            Some("--policy") => policy_path = args.next().map(PathBuf::from),
            Some("--public-key-hex") => {
                public_key_hex = args.next().and_then(|value| value.into_string().ok())
            }
            Some("--state-db") => state_db_path = args.next().map(PathBuf::from),
            Some("--transport") => {
                if args.next().as_deref() != Some(std::ffi::OsStr::new("stdio")) {
                    return Err(config_invalid());
                }
            }
            _ => return Err(config_invalid()),
        }
    }
    Ok(Config {
        policy_path: policy_path.ok_or_else(config_invalid)?,
        public_key_hex: public_key_hex.ok_or_else(config_invalid)?,
        state_db_path: state_db_path.ok_or_else(config_invalid)?,
    })
}

fn write_protocol_error(
    request_id: &str,
    error: ExecutorError,
) -> kolibri_storage_executor::Result<()> {
    write_response(&ErrorEnvelope {
        protocol_version: PROTOCOL_V1,
        request_id: request_id.to_owned(),
        ok: false,
        error: ErrorBody::from(&error),
    })
}

fn write_response(value: &impl serde::Serialize) -> kolibri_storage_executor::Result<()> {
    let mut output = serde_json::to_vec(value)?;
    output.push(b'\n');
    std::io::stdout().write_all(&output)?;
    std::io::stdout().flush()?;
    Ok(())
}

fn config_invalid() -> ExecutorError {
    ExecutorError::rejected(
        "executor_config_invalid",
        "The storage executor configuration is invalid.",
    )
}
