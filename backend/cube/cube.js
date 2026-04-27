// Cube config — see https://cube.dev/docs/config
// Phase 0: simple setup, single workspace.
// Phase 1: queryRewrite hook reads workspace JWT and applies access policies.

module.exports = {
  // Validate JWTs minted by query_service.
  checkAuth: async (req, auth) => {
    if (!auth) {
      throw new Error('Unauthorized: missing token');
    }
    // Cube auto-verifies HS256 with CUBEJS_API_SECRET.
    // We only need to attach security context here.
    req.securityContext = {
      workspace_id: auth.workspace_id,
      user_id: auth.user_id,
      attrs: auth.attrs || {},
    };
  },

  // Phase 1: enforce row-level security via securityContext.
  queryRewrite: (query, { securityContext }) => {
    return query;
  },

  // Schedule pre-aggregation refresh.
  scheduledRefreshTimer: 60,
};
