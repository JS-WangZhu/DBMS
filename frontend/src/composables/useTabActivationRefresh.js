import { onActivated } from "vue";

/**
 * Refresh remote page data whenever a keep-alive route is entered again.
 *
 * The initial activation is skipped because the page's onMounted hook already
 * performs its first load. Keeping the component alive preserves filters,
 * selections and unsaved form/editor input while the callback refreshes only
 * the remote data chosen by the page.
 */
export function useTabActivationRefresh(refresh) {
  let activatedOnce = false;
  let refreshing = false;

  onActivated(async () => {
    if (!activatedOnce) {
      activatedOnce = true;
      return;
    }
    if (refreshing || typeof refresh !== "function") {
      return;
    }

    refreshing = true;
    try {
      await refresh();
    } finally {
      refreshing = false;
    }
  });
}
