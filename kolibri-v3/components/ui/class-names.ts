export const uiClassTokens = {
	buttonBase:
		"inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-all outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
	inputBase:
		"h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-xs transition-[color,box-shadow] outline-none selection:bg-primary selection:text-primary-foreground file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:bg-input/30",
	inputFocusState:
		"focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
	inputInvalidState:
		"aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40",
	dialogOverlay:
		"fixed inset-0 z-50 bg-black/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
	dialogContent:
		"fixed top-[50%] left-[50%] z-50 grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border bg-background p-6 shadow-lg duration-200 outline-none data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 sm:max-w-lg",
	dialogCloseButton:
		"absolute top-4 right-4 rounded-xs opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
	threadListSearchInput:
		"h-9 rounded-lg border-transparent bg-black/[0.035] ps-8 text-sm shadow-none focus-visible:border-ring/40 dark:bg-white/[0.055]",
	threadListSearch:
		"relative px-0.5 py-1",
	threadListSearchIcon:
		"text-muted-foreground pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2",
	threadListItems:
		"flex flex-col gap-0.5",
	threadListSkeletonRow:
		"flex flex-col gap-0.5",
	threadListSkeletonItem:
		"flex h-9 items-center px-2.5",
	threadListSkeletonTile:
		"h-3.5 w-full",
	threadListItemsEmpty:
		"text-muted-foreground px-2.5 py-4 text-sm",
	threadListGroupLabel:
		"text-muted-foreground px-2.5 pt-3 pb-1 text-xs font-medium",
	threadListArchiveDetails:
		"group/archive mt-2",
	threadListArchiveSummary:
		"text-muted-foreground hover:bg-[var(--brand-soft)] flex h-8 cursor-pointer list-none items-center rounded-lg px-2.5 text-xs font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[color-mix(in_oklab,var(--brand)_45%,transparent)] dark:hover:bg-[var(--brand-soft)]",
	threadListArchiveBadge:
		"rounded-full bg-black/[0.045] px-1.5 py-0.5 text-[10px] dark:bg-white/[0.08]",
	threadListArchiveItems:
		"mt-0.5 flex flex-col gap-0.5",
	threadListNewButton:
		"h-10 justify-start gap-2 rounded-xl bg-foreground px-3 text-sm font-medium text-background shadow-sm hover:bg-foreground/88 data-active:bg-foreground",
	threadListMenuTrigger:
		"absolute end-1 top-1/2 flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground opacity-0 outline-none transition focus-visible:opacity-100 hover:bg-white/70 hover:text-foreground focus-visible:ring-2 focus-visible:ring-[color-mix(in_oklab,var(--brand)_50%,transparent)] group-hover:opacity-100 group-focus-within:opacity-100 group-data-active:opacity-100 data-[state=open]:bg-white/70 data-[state=open]:opacity-100 dark:hover:bg-white/10",
	threadListMenuItem:
		"flex cursor-default select-none items-center gap-2 rounded-lg px-2.5 py-2 outline-none data-[highlighted]:bg-[var(--brand-soft)] dark:data-[highlighted]:bg-[var(--brand-soft)]",
	threadListMenuContent:
		"z-[90] min-w-52 rounded-xl border bg-popover p-1.5 text-sm text-popover-foreground shadow-xl outline-none",
	threadListMenuCompactContent:
		"w-[min(17.5rem,calc(100vw-2rem))] rounded-[1.5rem] p-2 shadow-2xl",
	threadListItemHoverCardContent:
		"max-h-[min(22rem,calc(100dvh-1rem))] w-[min(20rem,calc(100vw-1rem))] overflow-y-auto overscroll-contain p-3",
	threadListItemMetaCard:
		"mt-3 space-y-2 rounded-lg bg-black/[0.025] p-2.5 text-xs dark:bg-white/[0.045]",
	threadListItemMetaRow:
		"text-muted-foreground flex items-start gap-2",
	threadListItemActionButton:
		"mt-3 h-8 w-full justify-center rounded-lg",
	generativeFallbackPanel:
		"rounded-lg border border-dashed border-border bg-muted/25 px-3 py-2 text-sm text-muted-foreground",
	generativeUIPanel:
		"min-w-0 rounded-xl border border-border/70 bg-card p-3",
	sidebarDestinationButton:
		"h-9 w-full justify-start gap-2.5 rounded-lg px-2 text-[14px] font-normal transition-colors hover:bg-[var(--brand-soft)] dark:hover:bg-[var(--brand-soft)]",
	sidebarBody:
		"min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-2.5 pt-1 pb-3",
	sidebarSectionHeading:
		"text-muted-foreground px-2 pb-1.5 text-sm font-normal",
	sidebarProfileFooter:
		"border-sidebar-border sticky bottom-0 z-20 mt-auto flex min-h-12 shrink-0 items-center border-t px-3 pb-[env(safe-area-inset-bottom)]",
	sidebarProfileTrigger:
		"flex min-w-0 flex-1 items-center rounded-lg px-1.5 py-1 text-left outline-none transition-colors hover:bg-[var(--brand-soft)] focus-visible:ring-[3px] data-[state=open]:bg-[var(--brand-soft-strong)] dark:hover:bg-[var(--brand-soft)]",
	sidebarProfileAvatar:
		"flex size-7 shrink-0 items-center justify-center rounded-full bg-[#fb927c] text-[10px] font-medium text-white",
	sidebarProfileName:
		"truncate text-sm leading-4 font-medium",
	sidebarProfileMeta:
		"text-muted-foreground truncate text-[10px] leading-3.5",
	sidebarProfileMenu:
		"z-[90] w-[min(20rem,calc(100vw-1rem))] rounded-xl border bg-popover p-1.5 shadow-xl",
	sidebarProfileMenuLabel:
		"px-2.5 py-2 font-normal",
	sidebarProfileMenuLabelInline:
		"flex items-center gap-2.5",
	sidebarProfileMenuName:
		"block truncate text-sm font-medium",
	sidebarProfileMenuEmail:
		"text-muted-foreground block truncate text-xs",
	threadListItem:
		"group relative flex min-h-9 items-center rounded-lg transition-[transform,background-color] duration-150 hover:bg-[var(--brand-soft)] focus-within:bg-[var(--brand-soft)] focus-visible:bg-[var(--brand-soft)] data-active:bg-[var(--brand-soft-strong)] data-[long-pressing=true]:scale-[0.985] data-[long-pressing=true]:bg-[var(--brand-soft-strong)] has-data-[state=open]:bg-[var(--brand-soft-strong)] dark:hover:bg-[var(--brand-soft)] dark:focus-within:bg-[var(--brand-soft)] dark:data-active:bg-[var(--brand-soft-strong)] dark:data-[long-pressing=true]:bg-[var(--brand-soft-strong)]",
	threadListItemTrigger:
		"flex h-full min-w-0 flex-1 items-center rounded-lg px-2.5 text-start text-[13px] outline-none group-hover:pe-9 group-focus-within:pe-9 group-has-data-[state=open]:pe-9 group-data-active:pe-9 focus-visible:ring-2 focus-visible:ring-ring/50",
	sidebarProfileMenuItem:
		"rounded-lg px-2.5 py-2 focus:bg-[var(--brand-soft)] dark:focus:bg-[var(--brand-soft)]",
	threadRoot:
		"aui-root aui-thread-root bg-background @container flex h-full min-h-0 min-w-0 flex-col overflow-hidden",
	threadViewport:
		"relative flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden overflow-y-auto overscroll-contain scroll-smooth",
	threadViewportContent:
		"mx-auto flex min-h-full w-[calc(100%-1.5rem)] min-w-0 max-w-(--thread-max-width) flex-1 flex-col pt-4",
	threadEmptyState:
		"flex min-h-0 flex-1 items-center justify-center py-6",
	threadMessageGroup:
		"mb-14 flex min-w-0 flex-col gap-y-6 empty:hidden",
	threadViewportFooter:
		"aui-thread-viewport-footer sticky bottom-0 z-10 mt-auto flex min-w-0 shrink-0 flex-col gap-3 overflow-visible rounded-t-(--composer-radius) bg-background pt-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))] md:pb-[calc(1rem+env(safe-area-inset-bottom))]",
	threadScrollToBottom:
		"aui-thread-scroll-to-bottom dark:border-border dark:bg-background dark:hover:bg-accent absolute -top-12 z-10 self-center size-11 md:size-9 rounded-full disabled:invisible",
	threadRunProgressPill:
		"border-border/70 bg-background text-muted-foreground mx-auto flex h-9 max-w-full items-center gap-2 rounded-full border px-4 text-xs shadow-[0_6px_20px_-14px_rgba(0,0,0,0.35)]",
	threadWelcomeRoot:
		"aui-thread-welcome-root mb-5 flex min-w-0 flex-col items-center px-2 text-center",
	threadWelcomeTitle:
		"aui-thread-welcome-message-inner text-2xl font-semibold tracking-tight sm:text-3xl",
	threadWelcomeText:
		"text-muted-foreground mt-2 max-w-xl text-sm leading-relaxed text-pretty sm:text-base",
	threadMobileStarterActions:
		"aui-mobile-starter-actions hidden w-full min-w-0 flex-col",
	threadWelcomeSuggestions:
		"aui-thread-welcome-suggestions flex w-full min-w-0 flex-wrap items-center justify-center gap-2",
	threadWelcomeSuggestionCard:
		"border-border/70 bg-muted/25 hover:bg-muted/55 focus-visible:ring-ring inline-flex min-h-9 min-w-0 items-center gap-2 rounded-full border px-4 py-2 text-start transition-colors outline-none focus-visible:ring-2",
	threadWelcomeSuggestionTitle:
		"text-foreground text-sm leading-snug font-medium whitespace-nowrap",
	threadWelcomeSuggestionDescription:
		"text-muted-foreground text-xs whitespace-nowrap",
	threadComposerRoot:
		"aui-composer-root relative flex w-full min-w-0 flex-col",
	threadComposerShell:
		"border-border/65 data-[dragging=true]:border-ring focus-within:border-ring/45 dark:border-muted-foreground/15 relative flex w-full min-w-0 flex-col gap-2 rounded-(--composer-radius) border bg-(--composer-bg) p-(--composer-padding) shadow-[0_12px_36px_-24px_rgba(0,0,0,0.45),0_2px_8px_-4px_rgba(0,0,0,0.12)] transition-[border-color,box-shadow] focus-within:shadow-[0_16px_40px_-24px_rgba(0,0,0,0.5),0_3px_10px_-4px_rgba(0,0,0,0.14)] data-[dragging=true]:border-dashed data-[dragging=true]:bg-[color-mix(in_oklab,var(--color-accent)_50%,var(--color-background))] dark:shadow-none [&_.aui-composer-attachments]:flex-wrap [&_.aui-composer-attachments]:overflow-x-hidden",
	threadComposerInput:
		"aui-composer-input caret-primary placeholder:text-muted-foreground/80 max-h-[200px] min-h-12 w-full min-w-0 resize-none overflow-x-hidden overflow-y-auto bg-transparent px-1.5 py-1 text-[15px] outline-none",
	threadComposerActionRow:
		"aui-composer-action-wrapper relative flex items-center justify-between",
	threadComposerLeadingActions:
		"aui-composer-leading-actions flex min-w-0 items-center gap-1",
	threadComposerTrailingActions:
		"aui-composer-trailing-actions flex items-center gap-1.5",
	threadActionButton:
		"aui-composer-action-button size-7 rounded-full",
	threadActionIcon:
		"aui-composer-action-icon size-4 stroke-[1.9px]",
	threadDictateIcon:
		"aui-composer-dictate-icon size-4",
	threadDictateFallback:
		"aui-composer-dictate aui-composer-dictate-fallback size-7 rounded-full",
	threadComposerSend:
		"aui-composer-send size-8 rounded-full",
	threadComposerSendEmpty:
		"aui-composer-send-empty",
	threadComposerCancel:
		"aui-composer-cancel size-7 rounded-full",
	threadComposerCancelIcon:
		"aui-composer-cancel-icon size-3.5 fill-current",
	threadAssistantMessageRoot:
		"fade-in slide-in-from-bottom-1 animate-in relative -mb-7.5 min-w-0 max-w-full pb-7.5 duration-150 [contain-intrinsic-size:auto_200px] [content-visibility:auto]",
	threadAssistantMessageContent:
		"text-foreground min-w-0 max-w-full overflow-hidden text-[15px] leading-[1.55] wrap-break-word",
	threadAssistantMessageFooter:
		"ms-2 flex items-center",
	threadAssistantActionBar:
		"aui-assistant-action-bar-root text-muted-foreground animate-in fade-in col-start-3 row-start-2 -ms-1 flex gap-1 duration-200",
	threadAssistantFeedbackSubmitted:
		"data-[submitted=true]:bg-accent data-[submitted=true]:text-foreground",
	threadReasoningStatus:
		"my-1.5",
	threadReasoningBlock:
		"aui-reasoning-block group/reasoning mt-2 overflow-hidden rounded-xl border border-border/70 bg-muted/35",
	threadReasoningSummary:
		"text-muted-foreground hover:text-foreground flex cursor-pointer select-none items-center justify-between gap-2 px-3 py-2 text-[13px] font-medium transition-colors outline-none",
	threadReasoningChevron:
		"size-3.5 opacity-60 transition-transform group-open/reasoning:rotate-180",
	threadReasoningBody:
		"text-muted-foreground border-t border-border/60 px-3 py-2.5 text-[13px] leading-5 whitespace-pre-wrap wrap-break-word",
	threadUserMessageRoot:
		"group/user fade-in slide-in-from-bottom-1 animate-in flex min-w-0 max-w-full flex-col items-end gap-y-1.5 duration-150 [contain-intrinsic-size:auto_200px] [content-visibility:auto] [&_.aui-user-message-attachments-end]:max-w-[78%] [&_.aui-user-message-attachments-end]:flex-wrap",
	threadUserMessageContentWrapper:
		"aui-user-message-content-wrapper relative w-fit max-w-[78%] min-w-0",
	threadUserMessageContent:
		"aui-user-message-content peer bg-[#f3f3f4] text-foreground rounded-xl rounded-tr-sm px-4 py-2 text-[15px] leading-[1.45] wrap-break-word empty:hidden dark:bg-[#2c2a28]",
	threadUserMeta:
		"text-muted-foreground flex min-h-5 items-center justify-end gap-1 text-[11px]",
	threadUserMetaRow:
		"text-muted-foreground flex min-h-5 items-center justify-end gap-1 text-[11px]",
	threadBranchPicker:
		"aui-branch-picker-root text-muted-foreground -ms-2 me-2 inline-flex items-center text-xs",
	threadUserActionBar:
		"aui-user-action-bar-root flex items-center",
	threadUserActionCopy:
		"aui-user-action-copy size-6 rounded-md",
	threadUserActionEdit:
		"aui-user-action-edit size-6 rounded-md",
	threadEditComposerRoot:
		"flex flex-col px-2 [contain-intrinsic-size:auto_200px] [content-visibility:auto]",
	threadEditComposerPanel:
		"aui-edit-composer-root border-border/60 dark:border-muted-foreground/15 ms-auto flex w-full max-w-[85%] flex-col rounded-(--composer-radius) border bg-(--composer-bg) shadow-[0_4px_16px_-8px_rgba(0,0,0,0.08),0_1px_2px_rgba(0,0,0,0.04)] dark:shadow-none",
	threadEditComposerInput:
		"aui-edit-composer-input text-foreground min-h-14 w-full resize-none bg-transparent px-4 pt-3 pb-1 text-base outline-none",
	threadEditComposerFooter:
		"aui-edit-composer-footer mx-2.5 mb-2.5 flex items-center gap-1.5 self-end",
	threadShareError:
		"border-border bg-background text-foreground absolute bottom-full left-0 z-30 mb-2 w-64 rounded-lg border px-3 py-2 text-xs leading-relaxed shadow-lg",
	threadMessageError:
		"aui-message-error-root border-destructive bg-destructive/10 text-destructive dark:bg-destructive/5 mt-2 rounded-md border p-3 text-sm dark:text-red-200",
	mobileHeaderRoot:
		"relative h-[6.5rem] shrink-0 bg-background",
	mobileHeaderContainer:
		"absolute inset-x-0 top-[calc(1.35rem+env(safe-area-inset-top))] flex items-center justify-between px-[15px]",
	mobileHeaderSpacer:
		"size-12 shrink-0",
	mobileHeaderHamburger:
		"flex w-6 flex-col gap-[7px]",
	mobileHeaderHamburgerBar:
		"h-[2.5px] w-full rounded-full bg-current",
	mobileHeaderDropdownContent:
		"z-[80] w-[min(17rem,calc(100vw-2rem))] rounded-[1.75rem] border-foreground/35 p-2 shadow-xl",
	mobileHeaderDropdownItem:
		"min-h-12 rounded-2xl px-4 text-[17px]",
	mobileHeaderDropdownLabel:
		"min-w-0 flex-1 truncate",
	workspaceSidebarShell:
		"text-sidebar-foreground flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden border-r border-[#dce5f5] bg-[#f2f6ff] dark:border-sky-950 dark:bg-[#101721]",
	workspaceHeaderRoot:
		"bg-background @container flex h-12 shrink-0 items-center gap-1.5 border-b px-3",
	workspaceHeaderDivider:
		"bg-border mx-1 h-6 w-px shrink-0",
	workspaceHeaderThreadTitle:
		"min-w-0 truncate text-[15px] font-semibold tracking-[-0.01em]",
	workspaceHeaderProjectButton:
		"h-7 max-w-44 gap-1.5 rounded-[10px] px-2.5 shadow-none",
	workspaceHeaderProjectLabel:
		"hidden min-w-0 truncate text-xs @min-[720px]:inline",
	workspaceHeaderProjectSecondary:
		"hidden min-w-0 truncate text-xs text-muted-foreground @min-[720px]:inline",
	workspaceHeaderMenuItemMeta:
		"block truncate text-xs font-medium",
	workspaceHeaderMenuItemSub:
		"text-muted-foreground block truncate text-[10px]",
	iconActionButton:
		"border-border hover:bg-muted focus-visible:ring-ring inline-flex size-9 shrink-0 items-center justify-center rounded-full border transition-colors focus-visible:ring-2 focus-visible:outline-none",
	generativeProvenanceNote:
		"mb-2 text-[10px] font-medium tracking-wide text-muted-foreground",
	generativeDetailsTrigger:
		"mt-2 text-xs text-muted-foreground",
	generativeSummary:
		"w-fit select-none rounded px-1 py-0.5 hover:bg-muted",
	generativeSource:
		"mt-1 max-h-56 overflow-auto rounded-lg border border-border bg-muted/35 p-3 text-[11px] leading-5",
	generativeUiContainerMinWidth:
		"min-w-0",
	presentationHeading2:
		"text-lg font-semibold tracking-tight",
	presentationHeading3:
		"text-base font-semibold",
	presentationHeading4:
		"text-sm font-semibold",
	generatedImageCard:
		"border-border/70 bg-card min-w-0 overflow-hidden rounded-[24px] border",
	generatedImageFigure:
		"bg-muted block aspect-square h-auto max-h-[680px] w-full object-contain",
	generatedImageCaption:
		"flex min-w-0 items-center gap-3 px-4 py-3",
	generatedImageStatus:
		"border-border/70 text-muted-foreground flex min-h-36 items-center justify-center gap-2 rounded-[24px] border text-sm",
	generatedImageError:
		"border-destructive/35 text-destructive rounded-xl border border-dashed px-4 py-3 text-sm",
} as const;
