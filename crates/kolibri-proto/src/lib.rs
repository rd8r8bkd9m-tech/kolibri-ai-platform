pub mod proto {
    tonic::include_proto!("kolibri.v1");
}

pub mod agent {
    tonic::include_proto!("kolibri.agent.v1");
}

pub mod node {
    tonic::include_proto!("kolibri.node.v1");
}

pub mod task {
    tonic::include_proto!("kolibri.task.v1");
}

pub mod event {
    tonic::include_proto!("kolibri.event.v1");
}

pub mod terminal {
    tonic::include_proto!("kolibri.terminal.v1");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn proto_modules_are_compiled() {
        let _ = proto::HealthResponse {
            status: String::new(),
            version: String::new(),
        };
        let _ = node::RegisterNodeResponse {
            node_id: String::new(),
            accepted: false,
        };
        let _ = task::CreateTaskResponse {
            task_id: String::new(),
            status: String::new(),
        };
    }

    #[test]
    fn proto_event_messages_compile() {
        let _ = event::PublishEventRequest {
            subject: String::new(),
            payload_json: String::new(),
            trace_id: String::new(),
        };
    }
}
