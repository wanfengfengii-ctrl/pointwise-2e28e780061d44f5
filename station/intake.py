from database import transaction
from station.ledger import load_acceptance, save_acceptance
from station.packet import check_initial_packet, initial_packet_identity


def accept_initial(db, packet):
    canonical = check_initial_packet(packet)
    with transaction(db):
        try:
            prior = load_acceptance(db, canonical.batch_id)
        except KeyError:
            return save_acceptance(db, canonical).acceptance_id
        if initial_packet_identity(prior.packet) != initial_packet_identity(canonical):
            raise ValueError('batch already has a different initial report')
        if prior.packet != canonical:
            raise ValueError('initial packet identity has conflicting contents')
        return prior.acceptance_id
