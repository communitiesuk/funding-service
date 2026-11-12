```
Title: Move existing pre_award python code into a top-level `pre_award` folder
Owner: Sarah Sloan
Collaborator(s): Platform Team
Created on: 10/01/2025
Status: Approved
Finalised on: 21/01/2025
```

## Overview

The platform team is looking to refactor, consolidate and simplify the code in the pre_award space. This includes changing the folder structure and file layout. In order to make it clear what parts of the code are written in the new format, and which are written in the existing format, this RFC proposes moving all existing code into a top level `pre_award` folder. There are no functional or architectural changes proposed in this RFC.

## What is the current state?

Currently the `funding-service-pre-award` repo has the folder structure shown below. This has a top level folder for each of the micro services that was lifted and shifted into this new monolith repo (eg. `account_store`, `apply` (formerly the `frontend` repo). The `tests` folder also contains a sub-folder for each of these micro services.

### funding-service-pre-award
![Screenshot 2025-01-10 at 11 22 20](https://github.com/user-attachments/assets/5183455b-c32f-463a-b966-52adaa3324d0)
### funding-service-pre-award/tests
![Screenshot 2025-01-10 at 11 24 07](https://github.com/user-attachments/assets/f139ddde-2d2d-4228-a346-d43d91ad8136)

## Why should we change?

This change is purely to provide signalling to developers working on the pre-award code base that during the consolidation there are 2 different structures in play. Having this separation at folder level will clarify what is using the new structure, and what is using the existing structure.


## How should we address this?

### Folder Structure
Move all existing code into a top level `pre_award` folder. Anything that is written in the new structure using new patterns will be stored outside this folder. As functionality is consolidated, code will be removed from the `pre_award` folder and replaced by code in the new structure. Eventually, we will reach a point where no changes are completed within the `pre_award` folder as everything is being consolidated, and then we will be able to remove the `pre_award` folder once it is empty.

The same principle would be applied to the `tests` directory, with all existing unit tests moved into a `tests/pre_award` directory, and new tests written in the `tests` directory.

The following screenshot shows the proposed new structure:

#### funding-service-pre-award
![Screenshot 2025-01-10 at 11 26 24](https://github.com/user-attachments/assets/53977105-30be-4e6e-85ca-5678554b83d8)

#### funding-service-pre-award/tests
![Screenshot 2025-01-10 at 11 26 41](https://github.com/user-attachments/assets/7f3388c0-0d9b-4fad-bfbb-11b309cb3c2c)

### General Approach
With this top level `pre_award` folder in place, the general approach would be to create new structures outside that folder. Gradually more code would live in this new structure and less under `pre_award`. Eventually we would cease to change `pre_award` so anything that is changed is moved to the new structure, finally deleting `pre_award/`. As an outline the steps would be:
- Platform team move existing code into `pre_award` folder
- Platform team to provide a concrete example of a vertical slice through the code (jinja templates through the database) for a specific piece of functionality.
- All teams to work in the following manner:
  - New functionality implemented in the new structure, following the example of how to layout code
  - Changes to existing functionality to work in the `pre_award` folder.
- Platform team to continue consolidating and migrating existing functionality to the new structure
- Stop changing anything in the `pre_award` folder - at this stage anything that is changed should be moved to the new structure
- Delete the `pre_award` folder.

This RFC does not specify a timescale on the above steps as this will depend on resource availability.

## What alternatives are we discarding?

- Keep the existing structure and just add new code alongside
This would  make it difficult to see what has been consodliated and moved to the new structure, and what still needs to be addressed. It will only add to developer confusion when the aim of this consolidation work is to make developers jobs easier.

- Moved everything into a folder named `deprecated`
Whilst this is functionally the same as the RFC proposal, the name 'deprecated' has many connotations and was deemed not to be appropriate as developers will still be working on changes in this folder for the immediate future. Also if priorities changed and this work was paused there is a potential for the `deprecated` folder be long-lived and naming it such would lead to further confusion.

- Leave existing code where it is and put new code in a folder called `new`
This was discarded for similar reasons to using a `deprecated` folder. If the work is paused, the name 'new' begins to lose its applicability. Also, at the end of consolidation, we would need to move everything out of `new`.

## Who will be affected?

This will only affect developers. Users will notice no change to functionality or appearance. The only functional change developers will notice is that the path for running any scripts will have changed. eg:
`python -m fund_store.scripts.amend_round_dates...` will become `python -m pre_award.fund_store.scripts.amend_round_dates...`


## Who will benefit?

Developers on the funding service. During the consolidation work platform team will be moving functionality into new structures and this change will send a clear message about what is written in the new way, and what is existing code from pre-consolidation.


## What are the key risks to manage or mitigate?

This is a low risk change. The main risk is functionality not working due to changed paths in the code, but this will be mitigated by running unit tests after the move, and also running our e2e tests.
