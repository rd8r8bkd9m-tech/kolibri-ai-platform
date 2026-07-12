use chrono::{DateTime, Utc};
use kolibri_core::{
    ActorMailbox, ActorMessage, ActorMessageKind, MailboxAck, MailboxEnqueue, MailboxError,
    WireMetadata, WireMetadataError,
};
use serde_json::json;
use uuid::Uuid;

fn at(seconds: i64) -> DateTime<Utc> {
    DateTime::from_timestamp(seconds, 0).expect("valid fixture timestamp")
}

#[test]
fn mailbox_deduplicates_dequeues_acks_checkpoints_and_replays_durably() {
    let actor_id = Uuid::new_v4();
    let mut mailbox = ActorMailbox::default();
    let first = mailbox
        .enqueue_once(
            actor_id,
            ActorMessageKind::Input,
            json!({"step":1}),
            "trace:mailbox",
            "message:1",
            at(1),
        )
        .expect("first enqueue");
    let second = mailbox
        .enqueue_once(
            actor_id,
            ActorMessageKind::Progress,
            json!({"step":2}),
            "trace:mailbox",
            "message:2",
            at(2),
        )
        .expect("second enqueue");
    mailbox
        .enqueue_once(
            actor_id,
            ActorMessageKind::PartialResult,
            json!({"step":3}),
            "trace:mailbox",
            "message:3",
            at(3),
        )
        .expect("third enqueue");
    assert!(matches!(
        first,
        MailboxEnqueue::Enqueued { sequence: 1, .. }
    ));
    let second_id = match second {
        MailboxEnqueue::Enqueued {
            message_id,
            sequence: 2,
        } => message_id,
        unexpected => panic!("unexpected enqueue result: {unexpected:?}"),
    };
    assert_eq!(
        mailbox
            .enqueue_once(
                actor_id,
                ActorMessageKind::Progress,
                json!({"different_payload_is_not_reapplied":true}),
                "trace:mailbox",
                "message:2",
                at(4),
            )
            .expect("duplicate is a successful no-op"),
        MailboxEnqueue::Duplicate {
            message_id: second_id,
            sequence: 2,
        }
    );
    assert_eq!(mailbox.messages.len(), 3);
    assert_eq!(mailbox.dequeue().map(|message| message.sequence), Some(1));

    assert_eq!(
        mailbox.ack(2).expect("out-of-order ack is recorded"),
        MailboxAck::RecordedOutOfOrder { sequence: 2 }
    );
    assert_eq!(mailbox.dequeue().map(|message| message.sequence), Some(1));

    let serialized = serde_json::to_vec(&mailbox).expect("serialize durable mailbox");
    let mut restored: ActorMailbox =
        serde_json::from_slice(&serialized).expect("restore durable mailbox");
    assert_eq!(
        restored
            .replay_from_checkpoint()
            .into_iter()
            .map(|message| message.sequence)
            .collect::<Vec<_>>(),
        vec![1, 3]
    );
    assert_eq!(
        restored.ack(1).expect("contiguous ack advances checkpoint"),
        MailboxAck::Advanced {
            through_sequence: 2,
        }
    );
    let checkpoint = restored
        .checkpoint("trace:mailbox", "mailbox-checkpoint:2", at(5))
        .expect("checkpoint metadata is valid");
    assert_eq!(checkpoint.schema_version, 1);
    assert_eq!(checkpoint.through_sequence, 2);
    assert_eq!(checkpoint.pending_sequences, vec![3]);
    assert_eq!(restored.compact_through_checkpoint(), 2);
    assert_eq!(restored.messages.len(), 1);

    assert_eq!(
        restored
            .enqueue_once(
                actor_id,
                ActorMessageKind::Progress,
                json!({"step":2}),
                "trace:mailbox",
                "message:2",
                at(6),
            )
            .expect("dedupe survives compaction"),
        MailboxEnqueue::Duplicate {
            message_id: second_id,
            sequence: 2,
        }
    );
    assert_eq!(
        restored.ack(3).expect("final ack advances checkpoint"),
        MailboxAck::Advanced {
            through_sequence: 3,
        }
    );
    assert_eq!(restored.dequeue(), None);
    assert_eq!(restored.ack(99), Err(MailboxError::UnknownSequence(99)));
}

#[test]
fn v1_wire_metadata_is_present_and_old_actor_messages_remain_readable() {
    let metadata = WireMetadata::v1("trace:wire", "wire:record:1");
    metadata.validate().expect("complete V1 metadata");
    assert_eq!(
        WireMetadata::v1("", "wire:record:1").validate(),
        Err(WireMetadataError::MissingTraceId)
    );
    assert_eq!(
        WireMetadata::v1("trace:wire", "").validate(),
        Err(WireMetadataError::MissingIdempotencyKey)
    );

    let legacy = json!({
        "id": Uuid::new_v4(),
        "actor_id": Uuid::new_v4(),
        "kind": "input",
        "sequence": 1,
        "payload": {"legacy":true},
        "trace_id": "trace:legacy",
        "created_at": at(1),
    });
    let message: ActorMessage =
        serde_json::from_value(legacy).expect("pre-idempotency V1 JSON stays readable");
    assert_eq!(message.schema_version, 1);
    assert!(message.idempotency_key.is_empty());

    let mut mailbox = ActorMailbox::default();
    mailbox
        .enqueue_once(
            Uuid::new_v4(),
            ActorMessageKind::Input,
            json!({}),
            "trace:new",
            "message:new",
            at(2),
        )
        .expect("new message");
    let message = &mailbox.messages[0];
    assert_eq!(message.schema_version, 1);
    assert_eq!(message.trace_id, "trace:new");
    assert_eq!(message.idempotency_key, "message:new");
}
