package PayloadEnvelope {
    private import ScalarValues::*;

    // Instrumentation backed by envelope_probe.py: `sample` counts each
    // runtime evaluation of a send argument and folds the count into its
    // result; `keep` records the whole payload value it receives.
    calc def sample { in value : Integer; return : Integer; }
    calc def keep { in payload : Meta; return : Boolean; }
    calc def keep_marker { in payload : Ping; return : Boolean; }

    // Field names that Sismic's event API reserves (`name`, `data`) or
    // interprets as scheduling (`delay`).
    item def Meta {
        attribute name : String;
        attribute data : Integer;
        attribute delay : Real default 2.5;
    }
    item def Tagged :> Meta {
        attribute extra : Integer default 3;
    }
    attribute def Inner {
        attribute name : String default "inner";
        attribute delay : Real default 1.5;
    }
    item def Wrapped {
        attribute data : Integer default 6;
        attribute inner : Inner;
    }
    item def Ping;

    // A self-send: arguments evaluate once, at the send; the event arrives
    // at the current logical time with exact field values.
    state def SelfSend {
        attribute current : Integer := 1;
        attribute capturedName : String := "";
        attribute capturedData : Integer := -1;
        attribute capturedDelay : Real := -1.0;
        attribute kept : Boolean := false;
        port commPort;
        // Checked by Sismic's contract machinery with the payload reader
        // in the copied context.
        assert constraint sane { capturedData >= -1 }
        entry;
            then idle;
        state idle {
            entry assign current := 40;
        }
        state armed {
            entry assign current := 100;
        }
        state received;
        transition first idle
            do send new Meta(name = "n", data = sample(current)) to commPort
            then armed;
        transition first armed
            accept r : Meta via commPort
            do action {
                assign capturedName := r.name;
                then assign capturedData := r.data;
                then assign capturedDelay := r.delay;
                then assign kept := keep(r);
            }
            then received;
    }

    // A subtype send accepted through its base type, and a nested value
    // whose structured field uses reserved names too.
    state def InheritedNested {
        attribute capturedName : String := "";
        attribute kept : Boolean := false;
        attribute innerName : String := "";
        attribute innerDelay : Real := -1.0;
        attribute wrappedData : Integer := -1;
        port commPort;
        entry;
            then idle;
        state idle;
        state tagged;
        state wrapped;
        state received;
        transition first idle
            do send new Tagged(name = "t", data = 8, delay = 0.5) to commPort
            then tagged;
        transition first tagged
            accept r : Meta via commPort
            do action {
                assign capturedName := r.name;
                then assign kept := keep(r);
                then send new Wrapped() to commPort;
            }
            then wrapped;
        transition first wrapped
            accept w : Wrapped via commPort
            do action {
                assign innerName := w.inner.name;
                then assign innerDelay := w.inner.delay;
                then assign wrappedData := w.data;
            }
            then received;
    }

    // A named marker payload read whole.
    state def MarkerWhole {
        attribute kept : Boolean := false;
        port commPort;
        entry;
            then idle;
        state idle;
        state armed;
        state received;
        transition first idle do send new Ping() to commPort then armed;
        transition first armed
            accept p : Ping via commPort
            do assign kept := keep_marker(p)
            then received;
    }

    // An externally injected payload with reserved field names.
    state def External {
        attribute capturedName : String := "";
        attribute capturedData : Integer := -1;
        attribute capturedDelay : Real := -1.0;
        attribute kept : Boolean := false;
        entry;
            then waiting;
        state waiting;
        state received;
        transition first waiting
            accept r : Meta
            do action {
                assign capturedName := r.name;
                then assign capturedData := r.data;
                then assign capturedDelay := r.delay;
                then assign kept := keep(r);
            }
            then received;
    }

    state def PeerSenderBehavior {
        attribute current : Integer := 1;
        port outPort;
        entry;
            then idle;
        state idle {
            entry assign current := 40;
        }
        state sent {
            entry assign current := 100;
        }
        transition first idle
            do send new Meta(name = "peer", data = sample(current), delay = 9.0)
                via outPort
            then sent;
    }
    state def PeerReceiverBehavior {
        attribute capturedName : String := "";
        attribute capturedData : Integer := -1;
        attribute capturedDelay : Real := -1.0;
        attribute kept : Boolean := false;
        port rxPort;
        entry;
            then waiting;
        state waiting;
        state received;
        transition first waiting
            accept r : Meta via rxPort
            do action {
                assign capturedName := r.name;
                then assign capturedData := r.data;
                then assign capturedDelay := r.delay;
                then assign kept := keep(r);
            }
            then received;
    }
    part def PeerSender {
        port outPort;
        exhibit state : PeerSenderBehavior;
    }
    part def PeerReceiver {
        port rxPort;
        exhibit state : PeerReceiverBehavior;
    }
    part peerSystem {
        part tx : PeerSender;
        part rx : PeerReceiver;
        connect tx.outPort to rx.rxPort;
    }
}
