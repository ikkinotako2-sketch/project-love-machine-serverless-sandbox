// Owner-created bootstrap placeholder only. No DB binding, outgoing HTTP,
// OAuth, SNS client, dispatch or secret is needed. Every request stays stopped.
export default {
  fetch() {
    return Response.json({status:'disabled',TEST_ONLY:true,DRY_RUN:true,
      NO_PUBLISH:true,EMERGENCY_STOP:true},{status:503});
  }
};
