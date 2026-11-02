package EventlessPriority {
    private import ScalarValues::*;

    state def FirstTrue {
        attribute chosen : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then active;
        state active { exit action { assign exits := exits + 1; } }
        state left { entry action { assign chosen := 1; } }
        state right { entry action { assign chosen := 2; } }
        transition first active if true
            do assign effects := effects + 1 then left;
        transition first active if true
            do assign effects := effects + 1 then right;
    }

    state def Reversed {
        attribute chosen : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then active;
        state active { exit action { assign exits := exits + 1; } }
        state left { entry action { assign chosen := 1; } }
        state right { entry action { assign chosen := 2; } }
        transition first active if true
            do assign effects := effects + 1 then right;
        transition first active if true
            do assign effects := effects + 1 then left;
    }

    state def FalseFirst {
        attribute chosen : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then active;
        state active { exit action { assign exits := exits + 1; } }
        state left { entry action { assign chosen := 1; } }
        state right { entry action { assign chosen := 2; } }
        transition first active if false
            do assign effects := effects + 1 then left;
        transition first active if true
            do assign effects := effects + 1 then right;
    }

    state def AllFalse {
        attribute chosen : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then active;
        state active { exit action { assign exits := exits + 1; } }
        state left { entry action { assign chosen := 1; } }
        state right { entry action { assign chosen := 2; } }
        transition first active if false
            do assign effects := effects + 1 then left;
        transition first active if false
            do assign effects := effects + 1 then right;
    }

    state def GuardlessFirst {
        attribute chosen : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then active;
        state active { exit action { assign exits := exits + 1; } }
        state left { entry action { assign chosen := 1; } }
        state right { entry action { assign chosen := 2; } }
        transition first active
            do assign effects := effects + 1 then left;
        transition first active if true
            do assign effects := effects + 1 then right;
    }

    state def GuardlessLast {
        attribute chosen : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then active;
        state active { exit action { assign exits := exits + 1; } }
        state left { entry action { assign chosen := 1; } }
        state right { entry action { assign chosen := 2; } }
        transition first active if true
            do assign effects := effects + 1 then left;
        transition first active
            do assign effects := effects + 1 then right;
    }

    state def GuardlessLastEligible {
        attribute chosen : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then active;
        state active { exit action { assign exits := exits + 1; } }
        state left { entry action { assign chosen := 1; } }
        state right { entry action { assign chosen := 2; } }
        transition first active if false
            do assign effects := effects + 1 then left;
        transition first active
            do assign effects := effects + 1 then right;
    }

    // The nested-scope transition is declared first, although the driver
    // emits the parent-scope transition first.
    state def NestedFirst {
        attribute chosen : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then outer;
        state outer {
            entry; then a;
            state a { exit action { assign exits := exits + 1; } }
            state b { entry action { assign chosen := 1; } }
            state c { entry action { assign chosen := 2; } }
            transition first a
                do assign effects := effects + 1 then b;
        }
        transition first outer.a
            do assign effects := effects + 1 then outer.c;
    }

    state def ParentFirst {
        attribute chosen : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then outer;
        transition first outer.a
            do assign effects := effects + 1 then outer.c;
        state outer {
            entry; then a;
            state a { exit action { assign exits := exits + 1; } }
            state b { entry action { assign chosen := 1; } }
            state c { entry action { assign chosen := 2; } }
            transition first a
                do assign effects := effects + 1 then b;
        }
    }

    // Each source picks its own first eligible declaration; the last step
    // reaches the root completion.
    state def Chain {
        attribute path : Integer := 0;
        attribute effects : Integer := 0;
        attribute exits : Integer := 0;
        entry; then s0;
        state s0 { exit action { assign exits := exits + 1; } }
        state s1 { exit action { assign exits := exits + 1; } }
        state s2 { exit action { assign exits := exits + 1; } }
        state trap;
        transition first s0 if false
            do assign effects := effects + 1 then trap;
        transition first s0 if true
            do action {
                assign effects := effects + 1;
                assign path := path * 10 + 1;
            } then s1;
        transition first s0 if true
            do assign effects := effects + 1 then trap;
        transition first s1
            do action {
                assign effects := effects + 1;
                assign path := path * 10 + 2;
            } then s2;
        transition first s1 if true
            do assign effects := effects + 1 then trap;
        transition first s2 if true
            do action {
                assign effects := effects + 1;
                assign path := path * 10 + 3;
            } then done;
        transition first s2
            do assign effects := effects + 1 then trap;
    }

    // A source with an `accept when` keeps its triggerless siblings
    // unranked, so simultaneously enabled candidates stay nondeterministic.
    state def WhenThenPlain {
        attribute hot : Boolean := false;
        attribute go : Boolean := false;
        entry; then active;
        state active;
        state viaWhen;
        state viaPlain;
        transition first active accept when hot then viaWhen;
        transition first active if go then viaPlain;
    }

    state def WhenThenTwoPlain {
        attribute hot : Boolean := false;
        attribute go : Boolean := false;
        entry; then active;
        state active;
        state viaWhen;
        state viaPlain1;
        state viaPlain2;
        transition first active accept when hot then viaWhen;
        transition first active if go then viaPlain1;
        transition first active if go then viaPlain2;
    }
}
