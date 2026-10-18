from celery import shared_task


@shared_task(ignore_result=True)
def reconcile_vendor_club_memberships(membership_id=None):
    """Rebuild vendor club balances from the point ledger.

    With a `membership_id`, reconciles that membership explicitly. Without
    one, reconciles every membership whose cached balances are past the
    sync interval. There is no beat schedule: due reconciliations also happen
    inline on `PointsService.get_membership`, and this task is the handle for
    operators and a future periodic job.
    """
    from domains.vendors_club.models import VendorClubMembership
    from domains.vendors_club.services import PointsService

    if membership_id is not None:
        membership = VendorClubMembership.objects.filter(pk=membership_id).first()
        if membership is not None:
            PointsService.sync_points(membership)
        return

    for membership in PointsService.due_memberships():
        PointsService.sync_points(membership)
