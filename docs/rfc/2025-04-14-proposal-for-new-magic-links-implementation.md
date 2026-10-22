```
Title: Proposal for new magic links implementation
Owner: Samuel Williams
Collaborator(s): The Platform Team
Created on: 03/04/2025
Status: Accepted
Finalised on: 14/04/2025
```

## Overview

This RFC covers proposals to aim for a simplified magic links authentication flow in the new funding-service app, when compared with the existing magic links flow on the current pre-award service.

## What is the current state?

Grant recipients need to log in to apply for funding. Each grant has a homepage with custom content for the grant and a button titled “Enter your email address” that takes them to an authenticator page that is personalised to the grant. Once they enter their email address, authenticator sends them a magic link (stored in redis) via email. The user clicks the link in the email and lands on a grant-specific page on authenticator that has a button they can click to claim/use the magic link. They are then finally redirected to the apply app again, onto a grant-specific landing page.

If a user visits an authentication-required page, and isn’t logged in, they see a page that says “you’re not logged in” with a button saying “request a new link” - goes to the authenticator login page.

## Why should we change?

This RFC recognises some main issues we think are worth addressing:
- The number of pages a user goes through when logging in is higher than it might need to be, and each of them has a lot of grant-specific context that feels repetitive when you step through the entire journey.
- We use redis to store magic links, and think that we don't need this infrastructure and should instead store the magic links in our standard postgres database.
- There is a significant amount of code supporting authentication/logging in and we think we can achieve similar functionality with less code to maintain.
  - The pre-award authentication journey still uses a bunch of 'API' endpoints and has a fairly broad code surface, which isn't really required at our scale.

## How should we address this?

(non-production-ready) examples of a streamlined magic links journey from the prototype:
- https://github.com/communitiesuk/funding-service-pre-award/blob/proto/base/proto/common/auth/__init__.py
- https://github.com/communitiesuk/funding-service-pre-award/blob/proto/base/proto/apply/web/__init__.py#L50-L109

The proposal for new magic link auth will roughly mean:

- All auth-required views are wrapped with a decorator that checks you're logged in (and later, with the correct permissions)
- That decorator will redirect you to a login page if required.
- Users enter their email address and submit the form, triggering an email and a 'check your emails' landing page.
- We store the magic link in postgres with a TTL of ~15 minutes or so.
- The user clicks the link in the email and comes to a landing page with JS to auto-claim the link.
- The magic link claim handler redirects to the user's original page and marks the link as used in the DB (don't delete the row).

## What alternatives are we discarding?

- Reproduce magic links journey+technology as-is.

## Who will be affected?

- End users (people logging in) should not notice a huge difference - the journey will feel quite similar, although they will hopefully need to go through fewer pages.
- Developers should find the authentication code easier to understand and update, because there is less of it.

## Who will benefit?

- MHCLG - simpler/smaller authentication gives a smaller attack/vulnerability surface. We've had some misconfiguration issues in the current pre-award code that led to significant potential risk (now mitigated/resolved).
- Developers - we think a simpler authentication flow will be easier to understand/maintain.

## What are the key risks to manage or mitigate?

- Building the new thing securely; choosing sensible algorithms, lifetimes, etc.
