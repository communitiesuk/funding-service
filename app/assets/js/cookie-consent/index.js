function gtag() {
    window.dataLayer.push(arguments);
}
function loadGoogleTag() {
    // Load Tag Manager script.
    var gtmScript = document.createElement("script");
    gtmScript.async = true;
    gtmScript.src =
        "https://www.googletagmanager.com/gtm.js?id=" + window.googleTagId;

    var firstScript = document.getElementsByTagName("script")[0];
    firstScript.parentNode.insertBefore(gtmScript, firstScript);
}
function initCookieConsent() {
    window.dataLayer = window.dataLayer || [];
    const cookie_banner = document.getElementById("cookie_banner");
    const cookie_choice_msg = document.getElementById("cookie_choice_msg");
    const cookies_rejected_msg = document.getElementById(
        "cookies_rejected_msg",
    );
    const cookies_accepted_msg = document.getElementById(
        "cookies_accepted_msg",
    );
    const accept_cookies_button = document.getElementById(
        "btn_accept_analytics_cookies",
    );
    const reject_cookies_button = document.getElementById(
        "btn_reject_analytics_cookies",
    );
    cookie_banner.removeAttribute("hidden");
    cookie_choice_msg.removeAttribute("hidden");

    accept_cookies_button.addEventListener("click", function () {
        localStorage.setItem("consentGranted", "true");

        gtag("consent", "update", {
            ad_user_data: "denied",
            ad_personalization: "denied",
            ad_storage: "denied",
            analytics_storage: "granted",
        });
    });
    reject_cookies_button.addEventListener("click", function () {
        localStorage.setItem("consentGranted", "false");
        gtag("consent", "update", {
            ad_user_data: "denied",
            ad_personalization: "denied",
            ad_storage: "denied",
            analytics_storage: "denied",
        });
    });
    loadGoogleTag();
}
initCookieConsent();
