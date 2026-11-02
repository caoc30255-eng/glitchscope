# Restore default diagnostics in this candidate project. Never downgrade errors.
puts "AX7010_COMPARE_LUT_MESSAGE_RULES_BEFORE"
get_msg_config -rules
reset_msg_config -severity ERROR -default_severity
# Restore inherited route-message suppression in this candidate as well.
reset_msg_config -id {Route 35-13} -suppress
reset_msg_config -id {Route 35-} -suppress
puts "AX7010_COMPARE_LUT_MESSAGE_RULES_AFTER_DEFAULT_RESTORE"
get_msg_config -rules
