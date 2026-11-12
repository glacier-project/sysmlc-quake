package Rejections {
    private import SI::*;
    private import ScalarValues::*;

    item def Go;

    part def Controller { port inPort; }
    part controller : Controller;

    // A send addressed to another occurrence cannot be delivered by a
    // single statechart; only the machine's own port is a self-send.
    state def MachineSendToPeer {
        entry;
            then idle;
        state idle;
        transition first idle do send new Go() to controller then done;
    }

    // A chained receiver (another machine's port) is cross-machine
    // addressing too.
    state def MachineSendToPeerPort {
        entry;
            then idle;
        state idle;
        transition first idle do send new Go() to controller.inPort then done;
    }

    // An eventless self-loop never stabilizes (nothing breaks the loop).
    state def MachineSelfLoop {
        entry;
            then idle;
        state idle;
        transition first idle then idle;
    }

    // A negative `after` duration is rejected.
    state def MachineNegDuration {
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept after -5 [s] then running;
    }

    // A state definition without an initial substate cannot be emitted as a
    // sismic compound state.
    state def MachineNoInitial {
        state idle;
        state running;

        transition first idle then running;
    }

    // Initial targets must be direct substates. Deep targets would require
    // decomposing initial choices across multiple sismic compound states.
    state def MachineDeepInitialQualifiedName {
        entry; then container::idle;

        state container {
            state idle;
            state running;
        }
    }

    state def MachineDeepInitialFeatureChain {
        entry; then container.idle;

        state container {
            state idle;
            state running;
        }
    }

    state def MachineDeepInitialConflict {
        entry; then running.hot;

        state running {
            entry; then warming;

            state warming;
            state hot;
        }
    }

    // A structured enumeration (the official ClassificationKind shape,
    // reduced to one field and one literal): the enum def specializes an
    // attribute def, so each literal carries `:>>` attribute redefinitions
    // instead of a single primitive value.
    attribute def ClassificationLevel {
        attribute code : String;
    }
    enum def ClassificationKind specializes ClassificationLevel {
        secret {
            :>> code = "secr";
        }
    }

    state def MachineStructuredEnum {
        attribute k : ClassificationKind := ClassificationKind::secret;
        entry;
            then idle;
        state idle;
    }

    action def Helper;

    // A referencing entry performs an action declared elsewhere; there is
    // no mapping yet, so it must not build as a state without `on entry`.
    state def MachineEntryReference {
        entry;
            then idle;
        state idle {
            entry helper;
        }
        action helper : Helper;
    }

    state def MachineExitReference {
        entry;
            then idle;
        state idle {
            exit helper;
        }
        action helper : Helper;
    }

    // A referencing transition effect performs an action declared elsewhere.
    state def MachineEffectReference {
        entry;
            then idle;
        state idle;
        state running;
        action helper : Helper;
        transition first idle do helper then running;
    }

    // A standalone succession (no `transition` keyword) is a transition
    // spelling that must not vanish.
    state def MachineStandaloneSuccession {
        entry;
            then idle;
        state idle;
        state running;
        first idle then running;
    }

    state def Sub {
        entry;
            then a;
        state a;
        state b;
    }

    // A state usage typed by a state def: flattening it to a leaf would
    // lose the def's content.
    state def MachineSubmachineUsage {
        entry;
            then s1;
        state s1 : Sub;
    }

    // An asserted constraint in a transition body has no mapping yet.
    state def MachineTransitionConstraint {
        attribute x : Integer := 1;
        entry;
            then idle;
        state idle;
        state running;
        transition first idle accept Go then running {
            assert constraint { x > 0 }
        }
    }

    state def MachineRootNamedState {
        entry;
            then MachineRootNamedState;
        state MachineRootNamedState;
    }

    state def MachineUnderscoreState {
        entry;
            then _hidden;
        state _hidden;
    }

    state def MachineShadowsMax {
        attribute max : Real := 2.0;
        entry;
            then idle;
        state idle;
    }
}
