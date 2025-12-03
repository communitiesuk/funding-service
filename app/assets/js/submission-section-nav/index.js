let scrollingFromUserClick = false;
let scrollTimeout;

const NAV_ITEM_CLASS = "app-section-nav-list__item";
const ACTIVE_NAV_ITEM_CLASS = "app-section-nav-list__item--active";

// trigger highlighting a section before you reach the exact top of the heading
const SCROLL_TOP_BUFFER_PIXELS = 100;
const DEBOUNCE_REFRESH_NAV_AFTER_SCROLL_CLICK_MS = 1500;

function selectNavItem(navItems, index) {
    navItems.forEach((item) => item.classList.remove(ACTIVE_NAV_ITEM_CLASS));
    navItems[index].classList.add(ACTIVE_NAV_ITEM_CLASS);
}

function refreshSelectedNavItem() {
    if (!scrollingFromUserClick) {
        const sections = document.querySelectorAll("h1[id], h2[id], table[id]");
        const navItems = document.querySelectorAll(`.${NAV_ITEM_CLASS}`);
        const scrollPosition = window.scrollY + SCROLL_TOP_BUFFER_PIXELS;
        let selected = false;

        sections.forEach((section, index) => {
            // we ignore making sure we're in the section bottom for now (offsetTop + offsetHeight)
            // as each new section should supersede the last, checking for this might refine the behaviour
            if (scrollPosition >= section.offsetTop) {
                selectNavItem(navItems, index);
                selected = true;
            }
        });

        // on mobile we might not be at a scroll position lower than anything, select the first thing
        // in theory on mobile theres not much point highlighting the nav as it will scroll out of view
        // this could also be resolved by setting the first item as active in the HTML
        if (!selected && window.scrollY < sections[0].offsetTop) {
            selectNavItem(navItems, 0);
        }
    }
}

function windowScrollIsBelowFooter() {
    const globalHeight = document.documentElement.clientHeight + window.scrollY;
    const scrollPosition =
        document.documentElement.scrollHeight ||
        document.documentElement.clientHeight;
    return (
        globalHeight >=
        scrollPosition - document.querySelector(".govuk-footer").offsetHeight
    );
}

function userClickScrollToNavItem(navItem) {
    const navItems = document.querySelectorAll(`.${NAV_ITEM_CLASS}`);
    const navItemLink = navItem.querySelector("a");
    const sectionIdFromNavLink = navItemLink.getAttribute("href").substring(1);
    const section = document.getElementById(sectionIdFromNavLink);

    if (section) {
        // window level state to block highlighting changes while acting
        scrollingFromUserClick = true;

        const navItemIndex = Array.from(navItems).indexOf(navItem);
        selectNavItem(navItems, navItemIndex);

        // by default link will stay focussed and highlighted (yellow) as it would
        // normally result in changing the page, as we're moving within the same page
        // remove this focus
        navItemLink.blur();

        section.scrollIntoView({ behavior: "smooth", block: "start" });

        // clear the previous timeout if we're clicking again within the debounce as we
        // don't want it to trigger until our new one is done
        clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => {
            scrollingFromUserClick = false;

            // clicking on the bottom few links will often overlap with the footer which means
            // we won't be "below" lower sections and will make the nav highlight jump around
            if (!windowScrollIsBelowFooter()) {
                refreshSelectedNavItem();
            }
        }, DEBOUNCE_REFRESH_NAV_AFTER_SCROLL_CLICK_MS);
    }
}

function configureNavScroll() {
    // overrides the default href on nav item links to smooth scroll to each section
    // this method also ensure what has been clicked is highlighted which may not get
    // highlighted by the default refresh towards the bottom of the page where you can't
    // scroll "past" the section
    document.querySelectorAll(`.${NAV_ITEM_CLASS}`).forEach((navItem) => {
        navItem.addEventListener("click", (e) => {
            // note when javascript is disabled the default href behaviour will not be be effected
            e.preventDefault();
            userClickScrollToNavItem(navItem);
        });
    });
    refreshSelectedNavItem();
}

function initSectionNavScroll() {
    const navItems = document.querySelectorAll(`.${NAV_ITEM_CLASS}`);
    if (navItems.length) {
        window.addEventListener("scroll", refreshSelectedNavItem);
        configureNavScroll();
    }
}

export { initSectionNavScroll };
