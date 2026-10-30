package TypedDispatch {
    private import ScalarValues::*;
    private import SI::*;
    item def '_tick_s_t1';
    item def Base { attribute value : Integer default 41; }
    item def Child :> Base;
    item def ExternalOnly :> Child;
    item def Other;
    package A { item def Twin :> Base; }
    package B { item def Twin :> Base; }

    package Left { attribute def Data { attribute x : Integer default 17; } }
    package Right { attribute def Data { attribute x : Integer default 29; } }
    item def Nested {
        attribute left : Left::Data;
        attribute right : Right::Data;
    }
    state def NestedPayload {
        port p;
        attribute captured : Integer := -1;
        entry; then ready;
        state ready;
        state waiting;
        state received;
        transition first ready do send new Nested() to p then waiting;
        transition first waiting accept packet : Nested
            do assign captured := packet.left.x + packet.right.x then received;
    }
    state def External {
        attribute captured : Integer := -1;
        entry; then waiting;
        state waiting;
        state received;
        transition first waiting accept packet : Base
            do assign captured := packet.value then received;
    }
    state def InnerFirst {
        attribute captured : Integer := -1;
        entry; then outer;
        state outer {
            entry; then waiting;
            state waiting;
            state received;
            transition first waiting accept packet : Base
                do assign captured := packet.value then received;
        }
        state escaped;
        transition first outer accept Child then escaped;
    }
    state def NestedFirst {
        attribute chosen : Integer := 0;
        entry; then outer;
        state outer {
            entry; then a;
            state a;
            state b;
            transition first a accept Base
                do assign chosen := 1 then b;
        }
        transition first outer.a accept Child
            do assign chosen := 2 then outer.b;
    }
    state def ParentFirst {
        attribute chosen : Integer := 0;
        entry; then outer;
        transition first outer.a accept Child
            do assign chosen := 2 then outer.b;
        state outer {
            entry; then a;
            state a;
            state b;
            transition first a accept Base
                do assign chosen := 1 then b;
        }
    }
    state def NestedFalseGuard {
        attribute chosen : Integer := 0;
        entry; then outer;
        state outer {
            entry; then a;
            state a;
            state b;
            transition first a accept Base if false
                do assign chosen := 1 then b;
        }
        transition first outer.a accept Child
            do assign chosen := 2 then outer.b;
    }
    state def TimerChannel {
        attribute chosen : Integer := 0;
        entry; then s;
        state s;
        state timed;
        state signaled;
        transition first s accept '_tick_s_t1'
            do assign chosen := 1 then signaled;
        transition first s accept after 1 [SI::s]
            do assign chosen := 2 then timed;
    }
    state def Sender {
        port tx;
        entry; then ready;
        state ready;
        transition first ready do send new Child() via tx then done;
    }
    state def BaseSink {
        port rx;
        attribute count : Integer := 0;
        attribute captured : Integer := -1;
        entry; then waiting;
        state waiting;
        state received;
        transition first waiting accept packet : Base via rx
            do action {
                assign count := count + 1;
                then assign captured := packet.value;
            } then received;
        transition first waiting accept Child via rx
            do assign count := count + 100 then received;
        transition first received accept Base via rx
            do assign count := count + 10 then received;
    }
    state def OtherSink {
        port rx;
        attribute count : Integer := 0;
        entry; then waiting;
        state waiting;
        state received;
        transition first waiting accept Other via rx
            do assign count := count + 1 then received;
    }
    part def Source { port tx; exhibit state : Sender; }
    part def Compatible { port rx; exhibit state : BaseSink; }
    part def Unrelated { port rx; exhibit state : OtherSink; }
    part system {
        part source : Source;
        part compatible : Compatible;
        part unrelated : Unrelated;
        connect source.tx to compatible.rx;
        connect source.tx to unrelated.rx;
    }
}
