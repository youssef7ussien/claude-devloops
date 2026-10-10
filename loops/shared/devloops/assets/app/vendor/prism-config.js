/* Prism's settings, read when prism-core loads (research R-16): never highlight the page by
   itself and never listen for worker messages. The app calls only Prism.tokenize. */
window.Prism = { manual: true, disableWorkerMessageHandler: true };
