function gtag() {
    window.dataLayer.push(arguments);
}

var googleTagLoaded = false;
function loadGoogleTag() {
    if (!googleTagLoaded) {
        // Load Tag Manager script.
        var gtmScript = document.createElement("script");
        gtmScript.async = true;
        gtmScript.src =
            "https://www.googletagmanager.com/gtm.js?id=" + window.googleTagId;

        var firstScript = document.getElementsByTagName("script")[0];
        firstScript.parentNode.insertBefore(gtmScript, firstScript);
        googleTagLoaded = true;
    }
}
function updateConsentValueLocal(consentGranted) {
    localStorage.setItem("consentGranted", consentGranted);
}
function updateConsentValueGtag(consentGranted) {
    gtag("consent", "update", {
        ad_user_data: "denied",
        ad_personalization: "denied",
        ad_storage: "denied",
        analytics_storage: consentGranted ? "granted" : "denied",
    });
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
    const btn_hide_cookies = document.getElementsByName("cookies[hide]");

    accept_cookies_button.addEventListener("click", function () {
        updateConsentValueLocal(true);
        updateConsentValueGtag(true);
        loadGoogleTag();
        cookie_choice_msg.hidden = true;
        cookies_accepted_msg.removeAttribute("hidden");
    });
    reject_cookies_button.addEventListener("click", function () {
        updateConsentValueLocal(false);
        updateConsentValueGtag(false);
        cookie_choice_msg.hidden = true;
        cookies_rejected_msg.removeAttribute("hidden");
    });
    btn_hide_cookies.forEach(function (value) {
        value.addEventListener("click", function () {
            cookie_banner.hidden = true;
        });
    });

    // only loads the google tag manager if consent has been provided
    // https://developers.google.com/tag-platform/security/concepts/consent-mode?#basic_consent_mode
    if (localStorage.getItem("consentGranted") === "true") {
        updateConsentValueGtag(true);
        loadGoogleTag();
    }
    if (!localStorage.getItem("consentGranted")) {
        cookie_banner.removeAttribute("hidden");
        cookie_choice_msg.removeAttribute("hidden");
    }
}

function initCookiesPageConsentForm() {
    const cookie_form = document.getElementById("cookies_form");

    if (cookie_form) {
        const cookies_no_js = document.getElementById("cookies_no_js");
        const cookies_yes = document.getElementById("cookie_choice_yes");
        const cookies_no = document.getElementById("cookie_choice_no");
        const cookie_success_banner = document.getElementById(
            "cookie_success_banner",
        );
        const btn_submit_cookie_form = document.getElementById(
            "btn_submit_cookies_form",
        );

        if (localStorage.getItem("consentGranted") === "true") {
            cookies_yes.checked = true;
        } else if (localStorage.getItem("consentGranted") === "false") {
            cookies_no.checked = true;
        }
        btn_submit_cookie_form.addEventListener("click", function () {
            let consentValue = cookies_yes.checked;
            updateConsentValueLocal(consentValue);
            updateConsentValueGtag(consentValue);
            cookie_success_banner.removeAttribute("hidden");
            cookie_success_banner.scrollIntoView();
        });

        cookies_no_js.hidden = true;
        cookie_form.removeAttribute("hidden");
    }
}

initCookieConsent();
initCookiesPageConsentForm();
