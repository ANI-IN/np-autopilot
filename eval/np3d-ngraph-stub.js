// The ngraph physics engine is NOT bundled: it compiles its integrators with
// `new Function`, which the site's CSP (no 'unsafe-eval') refuses. The map uses
// the d3 engine only; asking for ngraph fails loudly instead of silently.
function unavailable(){ throw new Error('ngraph engine not bundled (CSP: no unsafe-eval); use the d3 engine'); }
module.exports = unavailable;
module.exports.default = unavailable;
