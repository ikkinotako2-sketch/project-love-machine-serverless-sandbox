"""Pure read-only observation model; deadlines never authorize retry/posting."""
from datetime import datetime


def _time(value):
    if not isinstance(value, str):
        raise ValueError('invalid_time')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('invalid_time') from None
    if result.tzinfo is None:
        raise ValueError('timezone_required')
    return result


def observe_slot(observation, deadline, now):
    """collected/missed require explicit evidence. Missing is not zero metrics.

    An overdue pending observation is deadline_exceeded, not invented missed.
    Unknown is retained even after a deadline, requiring reconciliation.
    """
    due, current = _time(deadline), _time(now)
    if not isinstance(observation, dict) or set(observation) - {'status', 'evidence_id'}:
        raise ValueError('invalid_observation')
    status = observation.get('status', 'pending')
    if status not in ('pending', 'unknown', 'missed', 'collected'):
        raise ValueError('invalid_status')
    evidence = observation.get('evidence_id')
    if status in ('collected', 'missed'):
        from offline_readiness import _identifier
        _identifier(evidence)
    state = 'deadline_exceeded' if status == 'pending' and current > due else status
    action = {'pending': 'wait', 'deadline_exceeded': 'inspect_only', 'missed': 'inspect_only',
              'unknown': 'manual_reconciliation', 'collected': 'no_op'}[state]
    return {'state': state, 'deadline_exceeded': current > due, 'action': action,
            'auto_resend': False, 'posting_permitted': False}


def observe_metrics(slots, now):
    if not isinstance(slots, dict) or set(slots) != {'1h', '24h'}:
        raise ValueError('invalid_slots')
    return {key: observe_slot(slot['observation'], slot['deadline'], now)
            for key, slot in slots.items()}
