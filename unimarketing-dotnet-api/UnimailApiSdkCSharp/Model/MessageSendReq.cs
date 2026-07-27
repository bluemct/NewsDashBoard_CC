namespace Unimarketing.UnimailApiSdk.CSharp.Model
{
    public class MessageSendReq
    {
        /// <summary>
        ///     邮件主题
        /// </summary>
        public string Subject { get; set; }

        /// <summary>
        ///     邮件From地址
        /// </summary>
        public string From { get; set; }

        /// <summary>
        ///     邮件to地址
        /// </summary>
        public string To { get; set; }

        /// <summary>
        ///     内容类别 html / text
        /// </summary>
        public string ContentType { get; set; }


        /// <summary>
        ///     邮件回复地址
        /// </summary>
        public string Reply { get; set; }

        /// <summary>
        ///     邮件内容
        /// </summary>
        public string Content { get; set; }


        /// <summary>
        ///     邮件名称
        /// </summary>
        public string MessageName { get; set; }


        /// <summary>
        ///     联系人列表ID
        /// </summary>
        public string ListName { get; set; }
    }
}