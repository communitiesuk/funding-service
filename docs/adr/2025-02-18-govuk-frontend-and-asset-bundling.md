# GOV.UK Frontend and asset bundling

In our current systems, we download the GOV.UK Frontend zip file, unpack it, and then serve those pre-compiled assets directly. This makes it difficult to extend or modify those styles and components, but provides a simple developer experience.

We expect, as we develop a new integrated service, to need to override some variables that GOV.UK Frontend exposes or to build components and styles that extend what is provided natively. Doing this easily and effectively necessitates, to some degree, compiling and bundling GOV.UK Frontend from source.

There are a huge number of ways this could be achieved, as the JS/frontend web ecosystem tends to be fairly sprawling.

A few options are presented below to deal with our frontend JS/CSS needs.

## Options

### 1: Download GOV.UK Frontend zip, using the pre-compiled static files and assets

This option has been used by a number of the Funding Service frontends, as there is no transpilation of javascript/ SCSS necessary this is the simplest from a production build point of view and introduces no dependencies.

This option would not let us customise the GOV.UK Design System by extending the SCSS variables (i.e to change the width of the page while keeping all of the other styles consistent) instead requiring manually overriding the CSS styles. We would also need to re-run the extract and copy routine any time we changed the apps' styles.

### 2: Use eg DartSass to compile only CSS; reuse GOV.UK Frontend JS files directly

This option builds on the previous option but would introduce a bundling/ asset build process, either using a Python or Node library. At the time of writing `flask-assets` which is built on `web-assets` (and previously used by Funding Service frontends) has a number of longstanding open issues and doesn't appear to be well maintained, it also looks like it wouldn't support the newer version of Python used by the latest app.

### 3: Use a bundling system, eg Vite, to compile both CSS and JS from GOV.UK Frontend src.

Using the Node packages ecosystem would allow us to install a modern version of dart sass and directly create a dependency on the design system npm package (`govuk-frontend`).

This direct dependency can then be kept up to date by our version management process (currently `renovate`) and prompt us to upgrade when we need to.

Building from the SCSS and JavaScript allows us to safely extend the design system while keeping up to date with changes, and should reduce the amount of custom styles and code we need to write.

`vite` the frontend asset bundler also gives us the benefit of modern frontend tooling, providing:
- asset hashing for production builds
- hot module reloading for SCSS and JavaScript while developing, allowing developers to make small changes and see them immediately reflected
- TypeScript support if necessary

#### 3.a: Use an existing library `flask-vite`

We originally investigated using an existing library called `flask-vite`. This allowed us to get started very quickly but is designed around Single Page Applications (SPAs) which ended up having some drawbacks:
- as the output of an SPA is a single HTML/ JS target vite would serve development assets (even styles) through one JS file which was loaded and would then inject styles into the template, this caused a noticeable Flash of Unstyled Content during any page load and sets a precedent of the app not being performant
- additional styles/ code would have to be imported into the entry files and then all served at once, ideally we would be able to process files separately and either include them or not include them on any given page

#### 3.b: Configure vite ourselves

By adding our own `package.json` and creating a dependency on `vite` ourselves we take more control of the bundling and configuration. This allows us to:
- serve CSS and JS directly allowing the dev server to cache assets and the page to load appropriately
- have any number of assets which can be split up as required
- support different transpilation/ file types
- retain the good developer experience of the `vite` dev server

Importantly this option also allows our version management process (currently `renovate`) to suggest security and major upgrades to the asset build dependencies and GOV.UK Frontend.

## Decision

We will go for option 3.b, configuring and using `vite`. This should provide a clean and relatively simple developer experience, allowing us to extend and adjust GOV.UK Frontend styles and components as needed.
