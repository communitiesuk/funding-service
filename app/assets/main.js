import {initAll} from 'govuk-frontend';
import accessibleAutocomplete from 'accessible-autocomplete';
import {Swappable, Sortable} from '@shopify/draggable';

initAll();

for (let el of document.querySelectorAll("[data-accessible-autocomplete]")) {
    accessibleAutocomplete.enhanceSelectElement({
        selectElement: el, showAllValues: true, confirmOnBlur: false, displayMenu: "overlay",
    });
}

// distance: how far the mouse must be moved while clicked/held to start a drag; makes it possible to still click links that are in draggable containers
// mirror->constraintDimensions - keep the dragged mirror element the same size as its source
const sectionDrag = new Swappable(document.querySelectorAll('.fs-draggable-container'), {
    draggable: '.fs-draggable-item',
    mirror: {constrainDimensions: true},
    distance: 5,
    handle: '.fs-draggable-handle-section'
});

const taskDrag = new Sortable(document.querySelectorAll('.fs-draggable-container-task'), {
    draggable: '.fs-draggable-item-task',
    mirror: {constrainDimensions: true},
    distance: 5,
    handle: '.fs-draggable-handle-task'
});
