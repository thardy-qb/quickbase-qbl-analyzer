# Collection columns

The exact column names of every collection `query` reads. Names are matched
case-insensitively, but not abbreviated: `Parent Table` is not `Parent Table Name`.

This list comes from parsing reference exports. A column that only some
exports produce may be missing here; `collections <output-dir>` lists the
columns of your own run and is the final word.

## `application_settings`

`App Logical ID`, `App Name`, `Manager`, `App Icon`, `App Color`, `Currency Symbol`, `TableV3 State`, `TableV3 User Toggle State`, `Table Order`, `Cross Application Access`

## `application_variables`

`App Logical ID`, `Variable Logical ID`, `Type`, `Name`, `Value`

## `charts`

Chart metadata, a copy of the chart rows in `reports`.

`App Logical ID`, `Table Logical ID`, `Table Name`, `Table ID`, `Report Logical ID`, `Report ID`, `Report Name`, `Type`, `Description`, `Filters`, `Dynamic Fields`, `Sorting`, `Report Formulas`, `Used Last`, `Used Count`, `Used in Forms`, `Used in Dashboards`, `Object`

## `connected_table_fields`

Connected table field mappings.

`App Logical ID`, `Mapping #`, `Connected Table Logical ID`, `Connected Table Name`, `Connected Table ID`, `Table Field Logical ID`, `Table Field Name`, `Table Field ID`, `Table Field Type`, `Connected Column Logical ID`, `Connected Column Name`, `Connected Column ID`, `Connected Column Type`, `Record Set Logical ID`, `Record Set External ID`

## `connected_table_matrix`

Connected table-to-table references.

`App Logical ID`, `Connected Table Logical ID`, `Connected Table Name`, `Connected Table ID`, `Table Alias`, `Data Source Logical ID`, `Record Set Logical ID`, `Record Set External ID`, `Data Source Owner`, `Data Source Placeholder?`, `Field Map Count`, `Update Mode`

## `connected_tables`

Connected table metadata.

`App Logical ID`, `Connected Table Logical ID`, `Connected Table Name`, `Connected Table ID`, `Table Alias`, `Description`, `Connected?`, `Update Mode`, `Schedule Cron`, `Notify On Failure`, `Data Filter`, `Field Map Count`, `Key Fields`, `Data Source Logical ID`, `Data Source Type`, `Data Source Owner`, `Connection Param/Id`, `Data Source Placeholder?`, `Record Set Logical ID`, `Record Set External ID`, `Record Set Type`

## `custom_email_document_matrix`

Custom email-to-document template references (v0.14+).

No reference export populates this collection; run `collections` to see its columns.

## `custom_email_field_matrix`

Custom email-to-field references (v0.14+).

`App Logical ID`, `Table Logical ID`, `Custom Email Logical ID`, `Custom Email Name`, `Field Logical ID`, `Field ID`, `Usage Context`

## `custom_emails`

Custom email metadata (v0.14+).

`App Logical ID`, `Table Logical ID`, `Table Name`, `Custom Email Logical ID`, `Custom Email ID`, `Custom Email Name`, `Description`, `Owner`, `Trigger Type`, `Record Event Triggers`, `Schedule`, `Trigger Field Count`, `From`, `Bulk Change`, `Check Recipient Permissions`, `Send Scheduled Even When Empty`, `Subject`, `To Recipient Count`, `CC Recipient Count`, `BCC Recipient Count`, `Referenced Roles`, `Has Content`, `Content Length`, `File Attachment Count`, `Document Template Count`, `Condition Count`, `Has Conditions`

## `dashboards`

Dashboard widget metadata.

`App Logical ID`, `Dashboard Logical ID`, `Dashboard Name`, `Assigned to Role Homepage`, `Mapped to Role Permissions`, `Used by Roles`, `Tab Logical ID`, `Tab Name`, `Widget Logical ID`, `Widget Type`, `Widget Text`, `Widget Title`, `Widget ShowTitle`, `Widget BackgroundColor`, `Widget X`, `Widget Y`, `Widget Width`, `Widget Height`, `Target Table`, `Target Report`, `Target Page`, `Target App`, `NonDashboardPageId`, `AfterSaveAction`, `AfterSaveGoTo`, `Link`, `SearchType`, `SearchTarget`, `ResultsView`, `HintText`, `KpiType`, `IncludesDelta`, `ShowTarget`, `Scale`, `DecimalPlaces`, `TextColor`

## `document_templates`

Document template metadata (v0.14+).

`App Logical ID`, `Table Logical ID`, `Table Name`, `Document Template Logical ID`, `Document Template ID`, `Document Template Name`, `Description`, `Page Size`, `Orientation`, `Page Margins`, `Has Header`, `Has Footer`, `Content Length`

## `external_resource_columns`

`Resource Logical ID`, `Record Set Logical ID`, `Column Logical ID`, `Column Type`, `Column ID`

## `external_resource_recordsets`

`Resource Logical ID`, `Record Set Logical ID`, `Type`, `Set Type`, `External Set ID`, `Column Count`

## `external_resources`

`Resource Logical ID`, `Type`, `Owner`, `Connection Id`, `Is Placeholder`, `Record Set Count`, `Record Set Logical IDs`

## `field_form_matrix`

Field-to-form placement references.

`App Logical ID`, `Table Logical ID`, `Table ID`, `Table Name`, `Form Name`, `Form ID`, `Form Logical ID`, `Field Logical ID`, `Field Label`, `Field ID`, `Field Type`, `Form Page Logical ID`, `Form Page Name`, `Form Section Logical ID`, `Form Section Name`, `Form Column Logical ID`, `Form Row Logical ID`, `Form Element Logical ID`, `Form Element Label`, `Form Element Type`, `Element Order`, `Element Depth`, `Form Parent Path`, `Display Sequence`

## `field_pipeline_matrix`

Field-to-pipeline references.

`App Logical ID`, `Pipeline Logical ID`, `Pipeline Name`, `Step ID`, `Step Name`, `Table Logical ID`, `Table ID`, `Table Name`, `Field Logical ID`, `Field ID`, `Field Label`, `Field Type`, `Reference Context`

## `field_role_matrix`

Field-to-role permission references.

`App Logical ID`, `Table Logical ID`, `Table Name`, `Field Logical ID`, `Field ID`, `Field Label`, `Field Type`, `Role Logical ID`, `Role Name`, `Usage Type`, `Usage Context`

## `fields`

Field metadata and usage analysis.

`App Logical ID`, `Table Logical ID`, `Table ID`, `Table Name`, `Field Logical ID`, `Field ID`, `Field Label`, `Field Type`, `Field Help`, `Comments`, `Formula`, `Allowed in Reports`, `AllowCreateChoices`, `ChoiceOrder`, `Is Searchable`, `Is Required`, `Is Unique`, `Is Auditable`, `Is Formula Query`, `Other Properties`, `Lookup Relationship`, `Lookup Target Table`, `Lookup Target Table ID`, `Lookup Target Field`, `Lookup Target Field ID`, `Lookup Display As Link`, `Lookup Display Type`, `Summary Relationship`, `Summary Target Table`, `Summary Target Table ID`, `Summary Target Field`, `Summary Target Field ID`, `Summary Accumulation Type`, `Summary Formula`, `Field Caching Enabled`, `Field Caching Eligible`, `Is Used In Formula Query`, `Used in Reports`, `Used in Report Dynamic Filters`, `Used in Forms`, `Used in Form Rules`, `Used in Custom Data Rules`, `Referenced in Formulas`, `Used in Relationships`, `Used in Dashboards`, `Used in Charts`, `Used in Field Properties`, `Used in Permissions`, `Cross-App References`, `Total Usage Count`, `Total Usage Categories`, `Potentially Unused`, `Used in Pipelines`, `Used in Custom Emails`, `Used in Connected Tables`

## `forms`

Form metadata.

`App Logical ID`, `Table Logical ID`, `Table ID`, `Table Name`, `Form Logical ID`, `Form ID`, `Form Name`, `Assigned to Role (View/Edit/Add)`, `Description`, `Display Pages As`, `Auto Add Fields`, `Show Built-in Fields Footer`, `Always Tabs For View Record`, `Allowed Save Actions`, `Other Properties`, `Wait For Embedded Reports`, `New Field Action`

## `guides`

Application guide (custom help) metadata.

`App Logical ID`, `Guide Logical ID`, `Title`, `Description`, `Links To Page`

## `page_widgets`

Home page widgets, including the buttons, links and search fields they hold.

`App Logical ID`, `Page Logical ID`, `Page Name`, `Section`, `Row Logical ID`, `Row Order`, `Widget Order`, `Widget Logical ID`, `Widget Type`, `Parent Widget Logical ID`, `Title`, `Width`, `Points At`, `Url`

## `pages`

Page metadata.

`App Logical ID`, `Page Logical ID`, `Page ID`, `Page Name`, `Page Type`, `Assigned to Role Homepage`, `Mapped to Role Permissions`, `Used by Roles`, `Has Sidebar`, `Has Main Section`, `Total Widgets`, `Has Text`, `Text Length`, `Page Content`, `Has Code`, `Code Length`

## `parameter_definitions`

`Parameter Logical ID`, `Type`, `Description`, `Value`

## `permissions`

Table role permissions and default form/homepage settings.

`App Logical ID`, `Table Logical ID`, `Table ID`, `Role Logical ID`, `CanAddRecords`, `CanDeleteRecords`, `CanSaveCommonReports`, `CanEditFieldProperties`, `CanViewRecords`, `CanModifyRecords`, `View Form`, `Edit Form`, `Add Form`, `Grid Edit`, `Mobile`, `Home Page`, `CanRefreshConnectedData`

## `pipeline_steps`

Pipeline step metadata.

`App Logical ID`, `Pipeline Logical ID`, `Pipeline Name`, `Step ID`, `Step Name`, `Step Type`, `Step SubType`, `Account ID`, `Channel Type`, `Channel Resource`, `Channel ID`, `Channel Selector`, `HTTP Method`, `HTTP URL`, `HTTP Body`, `Content Type`, `Referenced Fields`, `Referenced Tables`, `Field Count`, `Table Count`, `Step Depth`, `Target Step ID`, `Table Logical ID`, `Table Name`, `Table Source`, `Filters`, `Input Mappings`, `Trigger Fields`, `Trigger On All Fields`

## `pipeline_table_matrix`

Pipeline-to-table references.

`App Logical ID`, `Pipeline Logical ID`, `Pipeline Name`, `Step ID`, `Step Name`, `Table Logical ID`, `Table ID`, `Table Name`, `Reference Type`, `Reference Context`

## `pipelines`

Pipeline metadata.

`App Logical ID`, `Pipeline Logical ID`, `Pipeline Name`, `Tags`, `Owner`, `Total Steps`, `Actions`, `Accounts`, `Description`, `Trigger`, `Schedule`, `Schedule Timezone`

## `relationships`

Relationship metadata.

`App Logical ID`, `Parent App Logical ID`, `Child App Logical ID`, `Relationship Logical ID`, `Parent Table Logical ID`, `Parent Table Name`, `Parent Table Alias`, `Child Table Logical ID`, `Child Table Name`, `Child Table Alias`, `Reference Field Logical ID`, `Reference Field ID`, `Reference Field Name`, `Reference Field Type`, `Relationship Type`, `Cross App`, `Parent Relationship ID`, `Total Reference Fields`, `Relationship Side`, `Counterpart Relationship Logical ID`, `Parent Table ID`, `Child Table ID`

## `report_dashboard_matrix`

Report-to-dashboard references.

`App Logical ID`, `Dashboard Logical ID`, `Dashboard Name`, `Tab Logical ID`, `Widget Logical ID`, `Report Reference`

## `report_duplicates`

`Duplicate Group`, `Duplicate Count`, `App Logical ID`, `Table Logical ID`, `Table Name`, `Table ID`, `Report Logical ID`, `Report ID`, `Report Name`, `Report Type`, `Filter Signature`, `Field Count`, `Field IDs`, `Field Labels`

## `report_field_matrix`

Report-to-field references.

`App Logical ID`, `Table Logical ID`, `Table ID`, `Table Name`, `Report Logical ID`, `Report ID`, `Report Name`, `Field Logical ID`, `Field ID`, `Field Label`, `Field Type`, `Used As`

## `report_groups`

Report group membership.

`App Logical ID`, `Table Logical ID`, `Table Name`, `Report Group Logical ID`, `Report Group Name`, `Report Count`, `Reports`

## `report_permissions`

Report role permissions.

`App Logical ID`, `Table Logical ID`, `Table ID`, `Table Name`, `Report Logical ID`, `Report ID`, `Report Name`, `Role Logical ID`, `Role ID`, `Role Name`, `Has Access`

## `reports`

Report and chart metadata; the `Object` column says which.

`App Logical ID`, `Table Logical ID`, `Table Name`, `Table ID`, `Report Logical ID`, `Report ID`, `Report Name`, `Type`, `Description`, `Filters`, `Dynamic Fields`, `Sorting`, `Report Formulas`, `Used Last`, `Used Count`, `Used in Forms`, `Used in Dashboards`, `Object`

## `role_form_rule_matrix`

Role references in form rules.

`App Logical ID`, `Table Logical ID`, `Table ID`, `Table Name`, `Form Name`, `Form ID`, `Form Logical ID`, `Rule ID`, `Rule Name`, `Rule Enabled`, `Role Logical ID`, `Role Name`, `Usage Type`, `Usage Context`

## `roles`

Application role metadata with usage flags.

`App Logical ID`, `Role Logical ID`, `Role ID`, `Role Name`, `Description`, `Default Role`, `Manage Users`, `Edit App`, `Disable Access`, `Restrict Access To New Tables`, `Used in Form Rules`, `Used in Table Permissions`, `Used in Field Permissions`, `Used in Report Permissions`, `Used in Default Forms`, `Used in Custom Access Rules`, `Referenced in Formulas`, `Used in Dashboard Permissions`, `Used in Pipeline Rules`, `Cross-App References`, `Total Usage Count`, `Potentially Unused`

## `rules`

Form rule metadata.

`App Logical ID`, `Table Name`, `Table Logical ID`, `Table ID`, `Form Name`, `Form Logical ID`, `Form ID`, `Rule ID`, `Rule Name`, `Enabled`, `Run On`, `Rule Summary`, `Condition Fields`, `Action Fields`, `When Conditions`, `If Conditions`, `Actions`

## `tables`

Table metadata.

`App Logical ID`, `Table Logical ID`, `Table ID`, `Table Name`, `Table Alias`, `updated`, `keyFieldId`, `sizeLimit`, `spaceUsed`, `spaceRemaining`, `Custom Data Rule`, `Custom Data Rule Enabled?`, `Table Description`
