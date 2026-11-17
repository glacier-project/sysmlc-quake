package StateNames {
    private import SI::*;
    private import ScalarValues::*;
    private import Time::TimeInstantValue;

    state def Timed {
        attribute deadlineTime : TimeInstantValue default 2 [s];
        entry; then 'S.1';
        state 'S.1';
        state 'S-1';
        state finished;
        transition first 'S.1' accept after 1 [s] then 'S-1';
        transition first 'S-1' accept at deadlineTime then finished;
    }

    state def Changed {
        attribute ready : Boolean := false;
        entry; then 'S.1';
        state 'S.1';
        state 'S-1';
        state finished;
        transition first 'S.1' accept when ready then 'S-1';
        transition first 'S-1' accept when not ready then finished;
    }

    state def Completed {
        entry; then 'S.1';
        state 'S.1' {
            entry; then waiting;
            state waiting;
            transition first waiting accept after 1 [s] then done;
        }
        state 'S-1' {
            entry; then waiting;
            state waiting;
            transition first waiting accept after 1 [s] then done;
        }
        state finished;
        transition first 'S.1' then 'S-1';
        transition first 'S-1' then finished;
    }
}
