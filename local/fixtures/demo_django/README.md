# demo_django

A small help desk used to test the scanner's Django support (TASKS T29).

- Roles: `customer` (signs up on the site), `support` (operator account given by the owner),
  `admin` (Django staff: `/admin/`, `/panel/*`; must never appear in a blueprint).
- The scanner must never open a `.env` file: the test makes a fake one in a temporary copy
  (env files are never committed).
- The scanner reads this folder as code only; it is never imported or run by the tests.
