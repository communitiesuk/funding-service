```
Title: Use generic templates in notify
Owner: @srh-sloan
Collaborator(s): @samuelhwilliams @MarcUsher @sfount
Created on: 15/11/2024
Status: Approved
Finalised on: 21/11/2024
```

# Overview
The funding service currently allows funds to customise the templates used to send emails from the 'Apply' part of the process. This customisation option has lead to complicated configuration in our notification micro service, but funds have not widely used this customisation option - most of our emails are already identical. The possibility of customisation means that a developer is needed when we onboard a new fund to setup the new templates.

This RFC proposes stopping the customisation of email templates on a per-fund basis, and having standard emails sent by Apply for the following scenarios:
- Requesting a magic link (already standardised)
- Application deadline reminder (already standardised)
- Application record of submission (current minor differences between funds)
- Incomplete application (currently all identical but defined multiple times)

## What is the current state?
Currently, an email template is defined for the following scenarios for each fund:
- Application record of submission - when you submit an application and we send you a copy of your answers
- Incomplete application - when the deadline for a round has passed and we send you a copy of any unsubmitted applications

The current approach means that every time we onboard a new fund, we need to:

1. Agree the content of each email
2. Create that template in Gov Notify
3. Add the ID of that new template to the configuration of the funding-service-design-notification service
4. Deploy that notification service to all environments.

## Why should we change?

The funding service has a goal to be able to onboard new funds without developer resource. The final 2 parts of the current approach listed above require a developer to make code changes, so this is not sustainable.

## How should we address this?
The content of the emails for both scenarios above is minimally different. We already have the ability to customise the content of an individual email with things like fund name, so I propose we have a single template for each email type that is used for all funds.

Agreed generic template: https://mhclg.sharepoint.com/:w:/s/FundingServiceDesignTeam/EZTiiF-9ZBhAhGW40fGbmKIBvFWKbyOsVTc1L6JSPrWJtw?e=eSrakt

## What alternatives are we discarding?

1. Keep the existing configuration setup - not an option as it requires developer resource to add new funds
2. Keep the current flexibility of defining a template per fund, and add these fund-specific template IDs to FAB for funds when they onboard
    1. Needs someone (very likely outside the fund team) to create a new template in notify for each fund, for each email we send, then copy and paste those IDs (GUIDs so not very user friendly and hard to spot any mistakes) into the config within FAB
    2. We would need to change the notification service to read this from a database as the IDs are currently hard coded. This would mean adding more fields to the fund store
    3. Maintains a high possibility for error in configuration and adds time to onboarding while discussions happen over the content of an email that doesn't need to be different for different funds.

## Who will be affected?
- Developers - no longer need to be involved in the notifcation part of onboarding a new fund
- Onboarding team - one less thing to discuss with a fund as it's one less thing they can customise
- Fund teams - a reduce level of flexibility, but it doesn't appear that this has ever been exploited beyond one sentence change for COF in the 'application record of submission' email.

## Who will benefit?
- Developers, as there is less configuration to manage
- Fund teams, as onboarding will be quicker
- Onboarding team and wider funding service - one less moving part in the onboarding journey for new funds

## What are the key risks to manage or mitigate?
- If this is approved and the work goes ahead, ensure the new generic templates are created and configured correctly before deploying this change to avoid any errors
- Ensure this is communicated to onboarding team so they have up to date information for new funds.
