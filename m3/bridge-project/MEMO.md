# Supplier review — Thursday payment run

```
SUPPLIER REVIEW · Thursday payment run · 7 suppliers · 8 of 9 lookups used

  REJECT        Al Wasel and Babel General Trading LLC
                This supplier matches a listed entity on the sanctions
                list, making payment illegal.

                → Rana: do not release payment
                Evidence (0 lookup(s)): 1.00 AL WASEL AND BABEL GENERAL
                TRADING LLC [programme: IRAQ2]

  REJECT        Zorblax Trading FZE
                There is no evidence that 'Zorblax Trading FZE' is a
                legitimate company, as both the LEI register and web
                search returned no results.

                → Rana: do not release payment
                Evidence (2 lookup(s)): gleif_lookup('Zorblax Trading
                FZE') returned: NO_RECORDS; web_search('Zorblax Trading
                FZE UAE') returned: NO_RESULTS.

  CONDITIONS    Almarai Company
                The LEI register returned no records, but independent
                evidence confirms it is a legitimate company; please
                provide a trade license or commercial registration number
                for payment.

                → Rana: Procurement to provide trade license or commercial
                registration number for Almarai Company
                Evidence (2 lookup(s)): LEI register returned NO_RECORDS;
                web search confirms Almarai Company is a legitimate Saudi
                multinational dairy company listed on the Tadawul stock
                exchange.

  CONDITIONS    C & V Works ApS
                The company is active but has a lapsed registration
                status, requiring confirmation of current registered
                details before payment can be released.

                → Rana: Confirm current registered details or renew the
                LEI for C & V Works ApS.
                Evidence (1 lookup(s)): LEI: 1595HU08XQEECLKNGF93, entity
                status: ACTIVE, registration status: LAPSED.

  CONDITIONS    Siemens AG
                The GLEIF register returned multiple candidates under
                'Siemens AG' without an exact match, requiring the LEI or
                registration number from the supplier's invoice for
                clarification.

                → Rana: Request the LEI or registration number from
                Procurement for the specific Siemens entity.
                Evidence (1 lookup(s)): GLEIF register: 10 candidate(s)
                under 'Siemens AG' - 0 exactly matching that name.

  APPROVE       Al Noor Cart Trading Company
                The supplier is legitimate with an active status and an
                issued LEI.

                → Rana: release payment to Al Noor Cart Trading Company
                Evidence (1 lookup(s)): LEI: 558600EWGLXU834B0P73, entity
                status: ACTIVE, registration status: ISSUED

  APPROVE       Maersk A/S
                The supplier is a legitimate entity with an active status
                and a valid LEI.

                → Rana: release payment to Maersk A/S
                Evidence (1 lookup(s)): LEI: 254900BLYIXBFFRLUJ90, entity
                status: ACTIVE, registration status: ISSUED

  PLAN · why the budget went where it did
                I prioritized suppliers with generic names and high
                sanctions similarity scores, as they are more likely to
                lead to a change in the decision upon lookup. Al Wasel and
                Babel General Trading LLC is ranked first due to its
                decisive sanctions match. The others follow based on their
                potential to reveal new information, with well-known
                brands like Maersk and Siemens ranked lower as they are
                less likely to change the outcome.

  LOOKUP LEDGER · 8 of 9 spent (sanctions screening is free and ran for all 7)
      1. gleif_lookup(Almarai Company)
      2. web_search(Almarai Company Saudi Arabia)
      3. gleif_lookup(Al Noor Cart Trading Company)
      4. gleif_lookup(Zorblax Trading FZE)
      5. web_search(Zorblax Trading FZE UAE)
      6. gleif_lookup(C & V Works ApS)
      7. gleif_lookup(Maersk A/S)
      8. gleif_lookup(Siemens AG)
```
