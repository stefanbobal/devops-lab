*======================================================================*
* Function group ZCERT_AGENT
* RFC interface of the certificate agent to the trust manager (STRUST).
*
*   Z_CERT_AGENT_GET_CERT   own certificate of a PSE (base64 DER)
*   Z_CERT_AGENT_CSR        certificate request for the existing key (PEM)
*   Z_CERT_AGENT_IMPORT     import the certificate response, save,
*                           distribute to all instances, notify the ICM
*
* The private key never leaves the system: only the request goes out
* and only signed certificates come in.
*
* ----------------------------------------------------------------------
* NOT ACTIVATED OR TESTED ON ANY SYSTEM.
* It is written from memory of what transaction STRUST does. Check these
* four points in SE37 on a sandbox before you activate it:
*
*   VERIFY 1  SSFPSE_FILENAME, SSFPSE_LOAD, SSFPSE_STORE, SSFPSE_ENQUEUE,
*             SSFPSE_DEQUEUE exist and have the parameters used below.
*   VERIFY 2  SSFC_GET_OWNCERTIFICATE returns the certificate as XSTRING.
*   VERIFY 3  SSFC_GET_CERTREQUEST and SSFC_PUT_CERTRESPONSE: the names of
*             the parameters, and the line type of the request / response
*             table. Put that line type into TY_PEM_LINE below. If the
*             lines are binary and not text, convert them in the two
*             marked places.
*   VERIFY 4  ICM_SSL_PSE_CHANGED: parameters and the type of CRED_NAME.
*
* The where-used list of SSFC_GET_CERTREQUEST shows how STRUST itself
* calls these modules; copy the call from there if it differs.
*
* How to create it:
*   - SE80: function group ZCERT_AGENT, three function modules,
*     processing type "Remote-Enabled Module", all parameters "Pass by value".
*   - Technical user: S_RFC for function group ZCERT_AGENT (plus the groups
*     the RFC library reads metadata from) and S_RZL_ADM with activity 01
*     and 03. Check the exact authorizations with a trace.
*======================================================================*

*======================================================================*
* TOP include
*======================================================================*
FUNCTION-POOL zcert_agent.

* VERIFY 3: line type of the tables CERTREQUEST / CERTRESPONSE
TYPES ty_pem_line  TYPE c LENGTH 255.
TYPES ty_pem_lines TYPE STANDARD TABLE OF ty_pem_line WITH DEFAULT KEY.


*======================================================================*
* Subroutines
*======================================================================*

* Only SSL server PSEs in version 1. SNC and system PSEs are refused here,
* whatever the caller asks for.
FORM check_allowed USING    iv_context  TYPE psecontext
                            iv_activity TYPE c
                   CHANGING cv_subrc    TYPE sysubrc.
  cv_subrc = 0.
  IF iv_context <> 'SSLS'.
    cv_subrc = 1.
    RETURN.
  ENDIF.
  AUTHORITY-CHECK OBJECT 'S_RZL_ADM' ID 'ACTVT' FIELD iv_activity.
  IF sy-subrc <> 0.
    cv_subrc = 2.
  ENDIF.
ENDFORM.

FORM pse_name USING    iv_context TYPE psecontext
                       iv_applic  TYPE ssfappl
              CHANGING cv_psename TYPE ssfpsename
                       cv_subrc   TYPE sysubrc.
  CALL FUNCTION 'SSFPSE_FILENAME'                           " VERIFY 1
    EXPORTING
      context       = iv_context
      applic        = iv_applic
    IMPORTING
      psename       = cv_psename
    EXCEPTIONS
      pse_not_found = 1
      OTHERS        = 2.
  cv_subrc = sy-subrc.
ENDFORM.

* Writes the PSE from the database into a temporary file on this server.
FORM pse_load USING    iv_psename  TYPE ssfpsename
              CHANGING cv_id       TYPE ssfid
                       cv_tempfile TYPE localfile
                       cv_subrc    TYPE sysubrc.
  CALL FUNCTION 'SSFPSE_LOAD'                               " VERIFY 1
    EXPORTING
      psename           = iv_psename
    IMPORTING
      id                = cv_id
      fname             = cv_tempfile
    EXCEPTIONS
      authority_missing = 1
      database_failed   = 2
      OTHERS            = 3.
  cv_subrc = sy-subrc.
ENDFORM.

FORM cleanup USING iv_tempfile TYPE localfile.
  IF iv_tempfile IS INITIAL.
    RETURN.
  ENDIF.
  TRY.
      DELETE DATASET iv_tempfile.
    CATCH cx_root.                                      "#EC NO_HANDLER
  ENDTRY.
ENDFORM.


*======================================================================*
FUNCTION z_cert_agent_get_cert.
*"----------------------------------------------------------------------
*"  IMPORTING
*"     VALUE(IV_CONTEXT)  TYPE  PSECONTEXT
*"     VALUE(IV_APPLIC)   TYPE  SSFAPPL
*"  EXPORTING
*"     VALUE(EV_CERT_B64) TYPE  STRING
*"  EXCEPTIONS
*"      PSE_NOT_ALLOWED
*"      NOT_AUTHORIZED
*"      PSE_NOT_FOUND
*"      KERNEL_ERROR
*"----------------------------------------------------------------------
  DATA: lv_psename  TYPE ssfpsename,
        lv_id       TYPE ssfid,
        lv_tempfile TYPE localfile,
        lv_profile  TYPE ssfpab,
        lv_cert     TYPE xstring,
        lv_subrc    TYPE sysubrc.

  PERFORM check_allowed USING iv_context '03' CHANGING lv_subrc.
  CASE lv_subrc.
    WHEN 1. RAISE pse_not_allowed.
    WHEN 2. RAISE not_authorized.
  ENDCASE.

  PERFORM pse_name USING iv_context iv_applic CHANGING lv_psename lv_subrc.
  IF lv_subrc <> 0.
    RAISE pse_not_found.
  ENDIF.
  PERFORM pse_load USING lv_psename CHANGING lv_id lv_tempfile lv_subrc.
  IF lv_subrc <> 0.
    RAISE pse_not_found.
  ENDIF.
  lv_profile = lv_tempfile.

  CALL FUNCTION 'SSFC_GET_OWNCERTIFICATE'                   " VERIFY 2
    EXPORTING
      profile               = lv_profile
    IMPORTING
      certificate           = lv_cert
    EXCEPTIONS
      ssf_krn_error         = 1
      ssf_krn_nomemory      = 2
      ssf_krn_nossflib      = 3
      ssf_krn_invalid_par   = 4
      ssf_krn_nocertificate = 5
      OTHERS                = 6.
  lv_subrc = sy-subrc.
  PERFORM cleanup USING lv_tempfile.
  IF lv_subrc <> 0.
    RAISE kernel_error.
  ENDIF.

  ev_cert_b64 = cl_http_utility=>encode_x_base64( lv_cert ).
ENDFUNCTION.


*======================================================================*
FUNCTION z_cert_agent_csr.
*"----------------------------------------------------------------------
*"  IMPORTING
*"     VALUE(IV_CONTEXT) TYPE  PSECONTEXT
*"     VALUE(IV_APPLIC)  TYPE  SSFAPPL
*"  EXPORTING
*"     VALUE(EV_CSR)     TYPE  STRING
*"  EXCEPTIONS
*"      PSE_NOT_ALLOWED
*"      NOT_AUTHORIZED
*"      PSE_NOT_FOUND
*"      KERNEL_ERROR
*"----------------------------------------------------------------------
* The request is made for the existing key pair. The PSE is not changed,
* so nothing is locked or saved here.
  DATA: lv_psename  TYPE ssfpsename,
        lv_id       TYPE ssfid,
        lv_tempfile TYPE localfile,
        lv_profile  TYPE ssfpab,
        lt_request  TYPE ty_pem_lines,
        lv_line     TYPE ty_pem_line,
        lv_subrc    TYPE sysubrc.

  PERFORM check_allowed USING iv_context '03' CHANGING lv_subrc.
  CASE lv_subrc.
    WHEN 1. RAISE pse_not_allowed.
    WHEN 2. RAISE not_authorized.
  ENDCASE.

  PERFORM pse_name USING iv_context iv_applic CHANGING lv_psename lv_subrc.
  IF lv_subrc <> 0.
    RAISE pse_not_found.
  ENDIF.
  PERFORM pse_load USING lv_psename CHANGING lv_id lv_tempfile lv_subrc.
  IF lv_subrc <> 0.
    RAISE pse_not_found.
  ENDIF.
  lv_profile = lv_tempfile.

  CALL FUNCTION 'SSFC_GET_CERTREQUEST'                      " VERIFY 3
    EXPORTING
      profile               = lv_profile
    TABLES
      certrequest           = lt_request
    EXCEPTIONS
      ssf_krn_error         = 1
      ssf_krn_nomemory      = 2
      ssf_krn_nossflib      = 3
      ssf_krn_invalid_par   = 4
      OTHERS                = 5.
  lv_subrc = sy-subrc.
  PERFORM cleanup USING lv_tempfile.
  IF lv_subrc <> 0 OR lt_request IS INITIAL.
    RAISE kernel_error.
  ENDIF.

* VERIFY 3: this assumes text lines (PEM). Convert here if they are binary.
  LOOP AT lt_request INTO lv_line.
    CONCATENATE ev_csr lv_line cl_abap_char_utilities=>newline INTO ev_csr.
  ENDLOOP.
ENDFUNCTION.


*======================================================================*
FUNCTION z_cert_agent_import.
*"----------------------------------------------------------------------
*"  IMPORTING
*"     VALUE(IV_CONTEXT)      TYPE  PSECONTEXT
*"     VALUE(IV_APPLIC)       TYPE  SSFAPPL
*"     VALUE(IV_RESPONSE)     TYPE  STRING
*"  EXPORTING
*"     VALUE(EV_ICM_NOTIFIED) TYPE  CHAR1
*"  EXCEPTIONS
*"      PSE_NOT_ALLOWED
*"      NOT_AUTHORIZED
*"      PSE_NOT_FOUND
*"      LOCK_FAILED
*"      IMPORT_REJECTED
*"      SAVE_FAILED
*"----------------------------------------------------------------------
* IV_RESPONSE: PEM text, own certificate first, then its CA certificates.
* The kernel refuses a certificate that does not belong to the key of the PSE.
  DATA: lv_psename  TYPE ssfpsename,
        lv_id       TYPE ssfid,
        lv_tempfile TYPE localfile,
        lv_profile  TYPE ssfpab,
        lt_strings  TYPE STANDARD TABLE OF string WITH DEFAULT KEY,
        lv_string   TYPE string,
        lt_response TYPE ty_pem_lines,
        lv_line     TYPE ty_pem_line,
        lv_subrc    TYPE sysubrc.

  PERFORM check_allowed USING iv_context '01' CHANGING lv_subrc.
  CASE lv_subrc.
    WHEN 1. RAISE pse_not_allowed.
    WHEN 2. RAISE not_authorized.
  ENDCASE.

* VERIFY 3: this assumes text lines (PEM). Convert here if they are binary.
  SPLIT iv_response AT cl_abap_char_utilities=>newline INTO TABLE lt_strings.
  LOOP AT lt_strings INTO lv_string.
    REPLACE ALL OCCURRENCES OF cl_abap_char_utilities=>cr_lf(1) IN lv_string WITH ``.
    IF lv_string IS NOT INITIAL.
      lv_line = lv_string.
      APPEND lv_line TO lt_response.
    ENDIF.
  ENDLOOP.
  IF lt_response IS INITIAL.
    RAISE import_rejected.
  ENDIF.

  PERFORM pse_name USING iv_context iv_applic CHANGING lv_psename lv_subrc.
  IF lv_subrc <> 0.
    RAISE pse_not_found.
  ENDIF.

  CALL FUNCTION 'SSFPSE_ENQUEUE'                            " VERIFY 1
    EXPORTING
      psename         = lv_psename
    EXCEPTIONS
      database_failed = 1
      foreign_lock    = 2
      internal_error  = 3
      OTHERS          = 4.
  IF sy-subrc <> 0.
    RAISE lock_failed.
  ENDIF.

  PERFORM pse_load USING lv_psename CHANGING lv_id lv_tempfile lv_subrc.
  IF lv_subrc <> 0.
    CALL FUNCTION 'SSFPSE_DEQUEUE' EXPORTING psename = lv_psename EXCEPTIONS OTHERS = 1.
    RAISE pse_not_found.
  ENDIF.
  lv_profile = lv_tempfile.

  CALL FUNCTION 'SSFC_PUT_CERTRESPONSE'                     " VERIFY 3
    EXPORTING
      profile             = lv_profile
    TABLES
      certresponse        = lt_response
    EXCEPTIONS
      ssf_krn_error       = 1
      ssf_krn_nomemory    = 2
      ssf_krn_nossflib    = 3
      ssf_krn_invalid_par = 4
      OTHERS              = 5.
  IF sy-subrc <> 0.
    PERFORM cleanup USING lv_tempfile.
    CALL FUNCTION 'SSFPSE_DEQUEUE' EXPORTING psename = lv_psename EXCEPTIONS OTHERS = 1.
    RAISE import_rejected.
  ENDIF.

* Save the changed PSE to the database and distribute it to all instances.
  CALL FUNCTION 'SSFPSE_STORE'                              " VERIFY 1
    EXPORTING
      fname             = lv_tempfile
      psename           = lv_psename
      id                = lv_id
      b_newdn           = abap_false
      b_distribute      = abap_true
    EXCEPTIONS
      file_load_failed  = 1
      storing_failed    = 2
      authority_missing = 3
      OTHERS            = 4.
  lv_subrc = sy-subrc.
  PERFORM cleanup USING lv_tempfile.
  CALL FUNCTION 'SSFPSE_DEQUEUE' EXPORTING psename = lv_psename EXCEPTIONS OTHERS = 1.
  IF lv_subrc <> 0.
    RAISE save_failed.
  ENDIF.

* Tell the ICM to reload the PSE. If this fails the certificate is saved
* but not active yet; the agent's TLS check will notice.
  CALL FUNCTION 'ICM_SSL_PSE_CHANGED'                       " VERIFY 4
    EXPORTING
      global              = 1
      cred_name           = lv_psename
    EXCEPTIONS
      icm_op_failed       = 1
      icm_get_serv_failed = 2
      icm_auth_failed     = 3
      OTHERS              = 4.
  IF sy-subrc = 0.
    ev_icm_notified = abap_true.
  ENDIF.
ENDFUNCTION.
